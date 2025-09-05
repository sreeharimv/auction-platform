
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify, Response, stream_with_context
import pandas as pd
from datetime import datetime
import os
import json
from werkzeug.utils import secure_filename
import io
from PIL import Image, ImageDraw, ImageFont
import threading
import queue

app = Flask(__name__)
app.secret_key = "change-me"

# Pillow resampling compatibility (handles Pillow<9.1 without Image.Resampling)
try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS  # Pillow 9.1+
except Exception:
    RESAMPLE_LANCZOS = getattr(Image, "LANCZOS", getattr(Image, "ANTIALIAS", Image.BICUBIC))

# Load configuration
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Return default config if file doesn't exist
        return {
            "tournament": {"name": "Palace Premier League", "logo": "logo.png"},
            "teams": {"count": 3, "names": ["Palace Tuskers", "Palace Titans", "Palace Warriors"], "budget": 25000000, "min_players": 8, "max_players": 9},
            "auction": {"base_price": 5000000, "currency": "₹", "increments": [1000000, 2500000, 5000000]}
        }

def save_config(config):
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

def parse_currency_input(value):
    """Convert formatted currency input (50L, 2.5Cr) to actual number"""
    if not value:
        return 0
    
    value = str(value).strip().upper().replace('₹', '').replace(',', '')
    
    if value.endswith('CR'):
        return int(float(value[:-2]) * 10000000)  # Crores
    elif value.endswith('L'):
        return int(float(value[:-1]) * 100000)    # Lakhs
    else:
        return int(float(value))  # Direct number

# Load config at startup
CONFIG = load_config()

# Dynamic configuration from config file
TEAM_BUDGET = CONFIG["teams"]["budget"]
BASE_PRICE = CONFIG["auction"]["base_price"]
TEAMS = CONFIG["teams"]["names"]

# Minimum role requirements per team
MIN_BATTERS = 2
MIN_BOWLERS = 2  
MIN_ALLROUNDERS = 2

# Current auction state (in-memory)
current_auction = {
    "player_id": None,
    "current_bid": 0,
    "current_team": "",
    "status": "waiting"  # waiting, bidding, going, sold
}

# Version counter for public live view; increments on state changes
auction_version = 0

def build_live_payload():
    """Build a minimal JSON-serializable payload representing live state."""
    df = load_players()
    payload = {
        "ts": datetime.now().isoformat(),
        "auction": {
            "status": current_auction.get("status"),
            "current_bid": current_auction.get("current_bid", 0),
            "current_team": current_auction.get("current_team") or "",
        },
        "starting_team": compute_starting_team(),
        "player": None,
        "eligible": [],
    }
    if current_auction.get("player_id"):
        row = df[df["player_id"] == current_auction["player_id"]]
        if not row.empty:
            p = row.iloc[0].to_dict()
            payload["player"] = {
                "id": int(p.get("player_id")),
                "name": p.get("name") or "",
                "role": p.get("role") or "",
                "base_price": int(p.get("base_price") or 0),
                "photo": p.get("photo") or "default.png",
            }
            limits = compute_team_limits(df, p, current_auction.get("current_bid", 0), current_team=current_auction.get("current_team", ""))
            # Only eligible teams; convert to list of dicts
            eligible = []
            for team, info in limits.items():
                if info.get("can_bid_now"):
                    eligible.append({
                        "team": team,
                        "max_valid_bid": int(info.get("max_valid_bid") or 0),
                        "remaining": int(info.get("remaining") or 0),
                        "players_with_captain": int(info.get("players_with_captain") or 0),
                        "near_limit": bool(info.get("near_limit")),
                    })
            # Sort eligible by highest max_valid_bid desc
            eligible.sort(key=lambda x: x["max_valid_bid"], reverse=True)
            payload["eligible"] = eligible
    return payload

def broadcast_state():
    """Increment version and push a JSON state payload to SSE listeners."""
    global auction_version
    auction_version += 1
    message = json.dumps({
        "type": "state",
        "version": auction_version,
        "payload": build_live_payload(),
    })
    with _sse_lock:
        for q in list(_sse_clients):
            try:
                q.put_nowait(message)
            except Exception:
                pass

# SSE subscription state
_sse_lock = threading.Lock()
_sse_clients = set()

def _subscribe_sse():
    q = queue.Queue(maxsize=100)
    with _sse_lock:
        _sse_clients.add(q)
    return q

def _unsubscribe_sse(q):
    with _sse_lock:
        _sse_clients.discard(q)

# Sequential auction state
sequential_auction = {
    "active": False,
    "current_index": 0,
    "player_sequence": []  # Will be populated with unsold player IDs
}

def format_indian_currency(amount):
    """Format currency in Indian format (50L, 1Cr, etc.)"""
    if amount == 0:
        return "0"
    
    amount = int(amount)
    if amount >= 10000000:  # 1 Crore or more
        crores = amount / 10000000
        # Show up to 2 decimals (e.g., 1.25Cr, 1.75Cr) and trim trailing zeros
        crores_rounded = round(crores + 1e-9, 2)  # tiny epsilon to avoid 1.249999
        s = f"{crores_rounded:.2f}".rstrip('0').rstrip('.')
        return f"{s}Cr"
    elif amount >= 100000:  # 1 Lakh or more
        lakhs = amount / 100000
        if lakhs == int(lakhs):
            return f"{int(lakhs)}L"
        else:
            return f"{lakhs:.1f}L"
    else:
        return f"₹{amount:,}"

def get_bid_increments(current_bid):
    """Generate valid bid increment options based on current bid relative to base price"""
    config = load_config()
    base_price = config["auction"]["base_price"]
    increments_config = config["auction"]["increments"]
    
    increments = []
    current = current_bid
    
    # Generate 10 increment options
    for i in range(10):
        increments.append(current)
        
        # Determine increment based on current price relative to base price
        if current < base_price * 2:  # Tier 1: Base to 2x Base
            current += increments_config[0]
        elif current < base_price * 4:  # Tier 2: 2x to 4x Base
            current += increments_config[1]
        else:  # Tier 3: 4x Base+
            current += increments_config[2]
    
    return increments

def get_auction_price_options(base_price):
    """Generate comprehensive price options for auction page"""
    config = load_config()
    increments_config = config["auction"]["increments"]
    
    options = []
    current = base_price
    
    # Generate 60 options to reach higher amounts
    for i in range(60):
        options.append(current)
        
        # Determine increment based on current price relative to base price
        if current < base_price * 2:  # Tier 1: Base to 2x Base
            current += increments_config[0]
        elif current < base_price * 4:  # Tier 2: 2x to 4x Base
            current += increments_config[1]
        else:  # Tier 3: 4x Base+
            current += increments_config[2]
    
    return options

# Make functions available in templates
import time
app.jinja_env.globals.update(int=int, format_currency=format_indian_currency, get_bid_increments=get_bid_increments, get_auction_price_options=get_auction_price_options, timestamp=lambda: int(time.time()), CONFIG=CONFIG)

# Add filter for replacing empty values with dash
@app.template_filter('dash_if_empty')
def dash_if_empty(value):
    return value if value and str(value).strip() and str(value) != 'nan' else '-'

# Helper to compute per-team max bid capacity for a given player and current bid
def compute_team_limits(df, player, current_bid, current_team=""):
    config = load_config()
    team_budget = config["teams"]["budget"]
    base_price_rule = config["auction"]["base_price"]
    max_players_allowed = config["teams"].get("max_players", 9)

    # Determine next required bids relative to current auction state
    effective_current = current_bid or 0
    no_leading_bid = (not current_team)
    if effective_current <= player["base_price"] and no_leading_bid:
        # First bid can be at base price
        min_next_bid = player["base_price"]
        incs_after_base = [p for p in get_bid_increments(player["base_price"]) if p > player["base_price"]]
        second_next_bid = incs_after_base[0] if incs_after_base else None
    else:
        next_prices = [p for p in get_bid_increments(effective_current) if p > effective_current]
        min_next_bid = next_prices[0] if next_prices else None
        second_next_bid = next_prices[1] if len(next_prices) > 1 else None

    team_limits = {}
    for team in TEAMS:
        team_mask = (df["team"] == team)
        spent = pd.to_numeric(df[team_mask]["sold_price"], errors="coerce").fillna(0).sum()
        sold_count = len(df[team_mask & (df["status"].str.lower() == "sold")])
        captain_count = len(df[team_mask & (df["status"].str.lower() == "captain")])

        remaining = int(team_budget - int(spent))

        # If already at or above max players (including captain), cannot bid
        if sold_count + captain_count >= max_players_allowed:
            max_bid = 0
        else:
            # Reserve budget for remaining slots AFTER buying this player (exclude captain and this player)
            reserve_slots = max(0, max_players_allowed - captain_count - sold_count - 1)
            max_bid = remaining - (reserve_slots * base_price_rule)
            max_bid = int(max(0, max_bid))

        if min_next_bid is None:
            can_bid_now = False
        else:
            can_bid_now = max_bid >= min_next_bid

        near_limit = can_bid_now and (second_next_bid is not None) and (max_bid < second_next_bid)

        # Compute highest valid bid reachable within increments (not exceeding max_bid)
        def next_step(val):
            if val < base_price_rule * 2:
                return val + config["auction"]["increments"][0]
            elif val < base_price_rule * 4:
                return val + config["auction"]["increments"][1]
            else:
                return val + config["auction"]["increments"][2]

        # Starting point: first required bid (min_next_bid). If no leading team and current at base, this is base.
        highest_valid = 0
        start = min_next_bid
        # If still none, nothing is reachable
        if start is not None and max_bid >= start:
            cand = start
            # Iterate up to a safe bound
            for _ in range(200):
                if cand <= max_bid:
                    highest_valid = cand
                else:
                    break
                new_val = next_step(cand)
                if new_val == cand:
                    break
                cand = new_val

        team_limits[team] = {
            "remaining": remaining,
            "players": sold_count,  # sold-only
            "players_with_captain": sold_count + captain_count,
            "max_bid": max_bid,
            "max_valid_bid": highest_valid,
            "can_bid": max_bid >= player["base_price"],
            "can_bid_now": can_bid_now,
            "near_limit": near_limit,
        }

    return team_limits

def get_next_required_bid(current_bid, base_price, has_leader):
    """Compute the next required bid amount based on increments and current state.
    If no leader, allow base/current shown as the first bid.
    """
    try:
        current_bid = int(current_bid or 0)
        base_price = int(base_price or 0)
    except Exception:
        return None
    if not has_leader:
        return current_bid if current_bid >= base_price else base_price
    for p in get_bid_increments(current_bid):
        if p > current_bid:
            return p
    return None

# Helper: compute starting team for current player in sequential auction
def compute_starting_team():
    try:
        if sequential_auction.get("active") and TEAMS:
            idx = sequential_auction.get("current_index", 0)
            return TEAMS[idx % len(TEAMS)]
    except Exception:
        pass
    return None

DATA_FILE = os.path.join(os.path.dirname(__file__), "players.csv")

def load_players():
    df = pd.read_csv(DATA_FILE)
    modified = False
    # Normalize expected columns / add if missing
    for col in ["team", "status", "sold_price", "sold_at", "photo"]:
        if col not in df.columns:
            df[col] = "" if col in ["team", "sold_at", "photo"] else 0 if col == "sold_price" else "unsold"
            modified = True
    # Ensure player_id is int-like
    if "player_id" in df.columns:
        try:
            df["player_id"] = df["player_id"].astype(int)
        except Exception:
            pass
    # Replace NaN/None with empty string for display
    df = df.fillna('')
    # Only write back if we actually added missing columns
    if modified:
        save_players(df)
    return df

def save_players(df):
    # Reorder columns for readability
    columns_order = ["player_id","name","age","role","batting_style","bowling_style","base_price","team","status","sold_price","sold_at","photo"]
    for c in columns_order:
        if c not in df.columns:
            df[c] = ""
    df = df[columns_order]
    df.to_csv(DATA_FILE, index=False)
    print(f"DEBUG: Saved players to {DATA_FILE}, file exists: {os.path.exists(DATA_FILE)}")

@app.route("/")
def index():
    df = load_players()
    auction_players = df[df["status"].astype(str).str.lower() != "captain"]
    total = len(auction_players)
    sold = (auction_players["status"].astype(str).str.lower() == "sold").sum()
    unsold = total - sold
    return render_template("index.html", total=total, sold=sold, unsold=unsold)

@app.route("/teams")
def teams():
    df = load_players()
    
    team_data = {}
    for team in TEAMS:
        team_players = df[df["team"] == team].to_dict(orient="records")
        # Sort players to show captain first
        team_players.sort(key=lambda x: (x.get("status", "") != "captain", x.get("name", "")))
        spent = pd.to_numeric(df[df["team"] == team]["sold_price"], errors="coerce").fillna(0).sum()
        team_data[team] = {
            "players": team_players,
            "count": len(team_players),
            "spent": int(spent),
            "remaining": TEAM_BUDGET - int(spent)
        }
    
    return render_template("teams.html", team_data=team_data, total_budget=TEAM_BUDGET)

@app.route("/players")
def players():
    df = load_players()
    sort = request.args.get("sort", "player_id")
    asc = request.args.get("asc", "1") == "1"
    if sort in df.columns:
        try:
            df = df.sort_values(by=sort, ascending=asc)
        except Exception:
            pass
    players = df.to_dict(orient="records")
    return render_template("players.html", players=players, sort=sort, asc=asc)

@app.route("/admin", methods=["GET", "POST"])
def admin():
    # Check if already logged in
    if session.get("is_admin"):
        return redirect(url_for("auction"))
    
    # Simple password check
    if request.method == "POST" and "password" in request.form:
        if request.form.get("password") == "admin123":
            session["is_admin"] = True
            return redirect(url_for("auction"))
        else:
            flash("Invalid password", "error")
    
    return render_template("admin_login.html")

@app.route("/auction", methods=["GET", "POST"])
def auction():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    df = load_players()

    if request.method == "POST":
        try:
            pid = int(request.form.get("player_id"))
        except (TypeError, ValueError):
            flash("Invalid player_id", "error")
            return redirect(url_for("auction"))

        action = request.form.get("action")
        if action == "sell":
            team = (request.form.get("team") or "").strip()
            price_raw = (request.form.get("sold_price") or "").replace(",", "").strip()
            try:
                sold_price = int(float(price_raw))
            except ValueError:
                flash("Enter a valid sold price (number).", "error")
                return redirect(url_for("auction"))

            idx = df.index[df["player_id"] == pid]
            if len(idx) == 0:
                flash("Player not found.", "error")
                return redirect(url_for("auction"))
            i = idx[0]
            if str(df.at[i, "status"]).lower() == "sold":
                flash("Player already sold.", "warning")
            else:
                # Check budget and minimum players requirement
                team_spent = pd.to_numeric(df[df["team"] == team]["sold_price"], errors="coerce").fillna(0).sum()
                team_players = len(df[(df["team"] == team) & (df["status"].str.lower().isin(["sold", "captain"]))])
                
                # Flexible squad completion logic (8-9 players per team)
                current_players = len(df[(df["team"] == team) & (df["status"].str.lower().isin(["sold", "captain"]))])
                
                # Check if team can still buy more players (max 9 per team)
                if current_players >= 9:
                    flash(f"{team} already has maximum 9 players!", "error")
                    return redirect(url_for("auction"))
                
                # Calculate remaining players needed (minimum 8, can go up to 9)
                total_players_left = len(df[df["status"].astype(str).str.lower() == "unsold"]) - 1  # Excluding this player
                total_assigned = sum(len(df[(df["team"] == t) & (df["status"].str.lower().isin(["sold", "captain"]))]) for t in TEAMS)
                
                # Ensure this team gets at least 8 players, but allow flexibility for 9
                min_needed = max(0, 8 - (current_players + 1))  # Minimum after this purchase
                players_needed_after_this = min_needed
                
                # Calculate max allowed bid
                remaining_budget = TEAM_BUDGET - team_spent
                max_allowed_bid = remaining_budget - (players_needed_after_this * BASE_PRICE)
                
                # Validate bid
                if team_spent + sold_price > TEAM_BUDGET:
                    flash(f"{team} budget exceeded! Remaining: ₹{format_indian_currency(remaining_budget)}", "error")
                elif sold_price > max_allowed_bid:
                    flash(
                        f"Max bid allowed: ₹{format_indian_currency(max_allowed_bid)} "
                        f"(Need ₹{format_indian_currency(players_needed_after_this * BASE_PRICE)} for {players_needed_after_this} more players)",
                        "error",
                    )
                else:
                    df.at[i, "team"] = team
                    df.at[i, "status"] = "sold"
                    df.at[i, "sold_price"] = sold_price
                    df.at[i, "sold_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_players(df)
                    # Broadcast update so viewers refresh teams/results
                    broadcast_state()
                    flash(f"Sold player #{pid} to {team} for ₹{format_indian_currency(sold_price)}.", "success")

        elif action == "revert":
            idx = df.index[df["player_id"] == pid]
            if len(idx) == 0:
                flash("Player not found.", "error")
                return redirect(url_for("auction"))
            i = idx[0]
            df.at[i, "status"] = "unsold"
            df.at[i, "team"] = ""
            df.at[i, "sold_price"] = 0
            df.at[i, "sold_at"] = ""
            save_players(df)
            broadcast_state()
            flash(f"Reverted sale for player #{pid}.", "info")

        return redirect(url_for("auction"))

    # GET - Calculate team budgets and player counts
    team_spending = {}
    for team in TEAMS:
        spent = pd.to_numeric(df[df["team"] == team]["sold_price"], errors="coerce").fillna(0).sum()
        players = len(df[(df["team"] == team) & (df["status"].str.lower().isin(["sold", "captain"]))])
        # Flexible team sizes (8-9 players)
        min_players = min(9, players + 1) if players < 8 else 9
        team_spending[team] = {
            "spent": int(spent), 
            "remaining": TEAM_BUDGET - int(spent),
            "players": players,
            "min_players": min_players
        }
    
    players_unsold = df[(df["status"].astype(str).str.lower() != "sold") & (df["status"].astype(str).str.lower() != "captain")].to_dict(orient="records")
    players_sold = df[df["status"].astype(str).str.lower() == "sold"].to_dict(orient="records")
    return render_template("auction.html", players_unsold=players_unsold, players_sold=players_sold, team_budgets=team_spending, total_budget=TEAM_BUDGET, base_price=BASE_PRICE, is_admin=True)

@app.route("/results")
def results():
    """Public view for audience - no admin controls"""
    df = load_players()
    
    # Calculate team budgets and player counts
    team_spending = {}
    for team in TEAMS:
        spent = pd.to_numeric(df[df["team"] == team]["sold_price"], errors="coerce").fillna(0).sum()
        players = len(df[(df["team"] == team) & (df["status"].str.lower().isin(["sold", "captain"]))])
        min_players = 8
        team_spending[team] = {
            "spent": int(spent), 
            "remaining": TEAM_BUDGET - int(spent),
            "players": players,
            "min_players": min_players
        }
    
    players_unsold = df[(df["status"].astype(str).str.lower() != "sold") & (df["status"].astype(str).str.lower() != "captain")].to_dict(orient="records")
    players_sold = df[df["status"].astype(str).str.lower() == "sold"].to_dict(orient="records")
    return render_template("auction.html", players_unsold=players_unsold, players_sold=players_sold, team_budgets=team_spending, total_budget=TEAM_BUDGET, is_admin=False, sold_first=True)

@app.route("/live-bidding/<int:player_id>", methods=["GET", "POST"])
def live_bidding(player_id):
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    player = df[df["player_id"] == player_id].iloc[0].to_dict()
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "start_bidding":
            current_auction["player_id"] = player_id
            current_auction["current_bid"] = player["base_price"]
            current_auction["current_team"] = ""
            current_auction["status"] = "bidding"
            broadcast_state()
            flash(f"Started bidding for {player['name']} at base price ₹{format_indian_currency(player['base_price'])}", "info")
            
        elif action == "update_bid":
            try:
                new_bid = int(request.form.get("bid_amount"))
            except (TypeError, ValueError):
                flash("Select a valid bid amount.", "error")
                return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=compute_team_limits(df, player, current_auction.get("current_bid", 0)))

            team = request.form.get("team") or ""
            if not team:
                flash("Select a team to place bid.", "error")
                return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=compute_team_limits(df, player, current_auction.get("current_bid", 0)))

            # Validate against team limits and increments
            limits = compute_team_limits(df, player, current_auction.get("current_bid", 0))
            tl = limits.get(team)
            if not tl:
                flash("Invalid team selection.", "error")
                return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=limits)

            current_bid_val = current_auction.get("current_bid", 0)
            current_team_val = current_auction.get("current_team", "")
            if current_team_val:
                # There is a leading bid; must outbid
                if new_bid <= current_bid_val:
                    flash("Bid must be higher than current bid.", "error")
                    return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=limits)
            else:
                # First bid can be at base price/current shown
                if new_bid < current_bid_val:
                    flash("Bid must be at least the current/base price.", "error")
                    return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=limits)

            if new_bid > tl["max_bid"]:
                flash(f"{team} cannot afford ₹{format_indian_currency(new_bid)}. Max allowed: ₹{format_indian_currency(tl['max_bid'])}", "error")
                return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=limits)

            # Server-side increment validation
            valid_next = [p for p in get_bid_increments(current_bid_val) if p > current_bid_val]
            # Allow selecting the current/base as first bid if no leading team
            if not current_team_val and current_bid_val >= player["base_price"]:
                valid_next.append(current_bid_val)
            if new_bid not in valid_next:
                flash("Invalid increment selected.", "error")
                return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=limits)

            # All good – apply bid
            current_auction["current_bid"] = new_bid
            current_auction["current_team"] = team
            current_auction["status"] = "bidding"
            broadcast_state()
            
        elif action == "sold":
            # If no bid placed, sell at base price
            if current_auction["current_bid"] == 0:
                current_auction["current_bid"] = player["base_price"]
                current_auction["current_team"] = request.form.get("team", "")
            # Validate sale against team limits
            sale_team = current_auction.get("current_team") or ""
            if not sale_team:
                flash("Cannot mark as SOLD without a leading team.", "error")
                return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=compute_team_limits(df, player, current_auction.get("current_bid", 0)))

            limits = compute_team_limits(df, player, current_auction.get("current_bid", 0))
            tl = limits.get(sale_team)
            if not tl or current_auction["current_bid"] > tl["max_bid"]:
                flash(f"{sale_team} cannot complete purchase at ₹{format_indian_currency(current_auction['current_bid'])}. Max: ₹{format_indian_currency(tl['max_bid']) if tl else 0}", "error")
                return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS, team_limits=limits)

            # Mark as sold in CSV
            idx = df.index[df["player_id"] == player_id][0]
            df.at[idx, "team"] = current_auction["current_team"]
            df.at[idx, "status"] = "sold"
            df.at[idx, "sold_price"] = current_auction["current_bid"]
            df.at[idx, "sold_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_players(df)
            
            # Reset auction state
            current_auction["player_id"] = None
            current_auction["current_bid"] = 0
            current_auction["current_team"] = ""
            current_auction["status"] = "waiting"
            broadcast_state()
            
            flash(f"SOLD! {player['name']} to {df.at[idx, 'team']} for ₹{format_indian_currency(df.at[idx, 'sold_price'])}", "success")
            
            # If in sequential auction, move to next player
            if sequential_auction["active"]:
                sequential_auction["current_index"] += 1
                if sequential_auction["current_index"] >= len(sequential_auction["player_sequence"]):
                    # End of round - if unsold players remain, start another round
                    df2 = load_players()
                    unsold_players = df2[(df2["status"].astype(str).str.lower() == "unsold")]
                    if len(unsold_players) > 0:
                        sequential_auction["current_index"] = 0
                        sequential_auction["player_sequence"] = unsold_players["player_id"].tolist()
                        next_player_id = sequential_auction["player_sequence"][0]
                        current_auction["player_id"] = next_player_id
                        current_auction["current_bid"] = BASE_PRICE
                        current_auction["current_team"] = ""
                        current_auction["status"] = "bidding"
                        broadcast_state()
                        flash("New round started for remaining unsold players.", "info")
                        return redirect(url_for("sequential_auction_page"))
                    else:
                        # Auction complete
                        sequential_auction["active"] = False
                        current_auction["player_id"] = None
                        current_auction["status"] = "waiting"
                        broadcast_state()
                        flash("Sequential auction completed! All players processed.", "success")
                        return redirect(url_for("auction"))
                # Set next player
                next_player_id = sequential_auction["player_sequence"][sequential_auction["current_index"]]
                current_auction["player_id"] = next_player_id
                current_auction["current_bid"] = BASE_PRICE
                current_auction["current_team"] = ""
                current_auction["status"] = "bidding"
                broadcast_state()
                return redirect(url_for("sequential_auction_page"))
            else:
                return redirect(url_for("auction"))
    
    team_limits = compute_team_limits(
        df,
        player,
        current_auction.get("current_bid", 0),
        current_team=current_auction.get("current_team", ""),
    )
    next_bid = get_next_required_bid(
        current_auction.get("current_bid", 0),
        player.get("base_price", 0),
        bool(current_auction.get("current_team")),
    )
    starting_team = compute_starting_team()

    return render_template(
        "live_bidding.html",
        player=player,
        auction_state=current_auction,
        teams=TEAMS,
        team_limits=team_limits,
        next_bid=next_bid,
        starting_team=starting_team,
    )

@app.route("/live-view")
def live_view():
    """Public live view of current bidding"""
    df = load_players()
    current_player = None
    team_limits = None
    starting_team = compute_starting_team()
    if current_auction["player_id"]:
        current_player = df[df["player_id"] == current_auction["player_id"]].iloc[0].to_dict()
        team_limits = compute_team_limits(
            df,
            current_player,
            current_auction.get("current_bid", 0),
            current_team=current_auction.get("current_team", ""),
        )
    
    return render_template("live_view.html", current_player=current_player, auction_state=current_auction, team_limits=team_limits, starting_team=starting_team, auction_version=auction_version)

@app.route("/start-sequential", methods=["POST"])
def start_sequential():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    # Get all unsold players (excluding captains)
    unsold_players = df[(df["status"].astype(str).str.lower() == "unsold")]
    
    if len(unsold_players) == 0:
        flash("No unsold players available for sequential auction!", "error")
        return redirect(url_for("auction"))
    
    # Check for custom order
    custom_order = request.form.get('custom_order')
    if custom_order:
        import json
        player_names = json.loads(custom_order)
        # Convert names to player IDs
        player_sequence = []
        for name in player_names:
            player_row = df[df['name'] == name]
            if not player_row.empty:
                player_sequence.append(player_row.iloc[0]['player_id'])
    else:
        # Use default strategic sequence
        player_sequence = unsold_players["player_id"].tolist()
    
    # Initialize sequential auction
    sequential_auction["active"] = True
    sequential_auction["current_index"] = 0
    sequential_auction["player_sequence"] = player_sequence
    
    # Set first player as current
    first_player_id = sequential_auction["player_sequence"][0]
    current_auction["player_id"] = first_player_id
    current_auction["current_bid"] = BASE_PRICE
    current_auction["current_team"] = ""
    current_auction["status"] = "bidding"
    broadcast_state()
    broadcast_state()
    
    flash(f"Sequential auction started! {len(sequential_auction['player_sequence'])} players in queue.", "success")
    return redirect(url_for("sequential_auction_page"))

@app.route("/sequential-auction")
def sequential_auction_page():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    if not sequential_auction["active"]:
        flash("No sequential auction in progress!", "error")
        return redirect(url_for("auction"))
    
    df = load_players()
    current_player = None
    
    if current_auction["player_id"]:
        current_player = df[df["player_id"] == current_auction["player_id"]].iloc[0].to_dict()
    
    # Calculate team budgets
    team_spending = {}
    for team in TEAMS:
        spent = pd.to_numeric(df[df["team"] == team]["sold_price"], errors="coerce").fillna(0).sum()
        players = len(df[(df["team"] == team) & (df["status"].str.lower().isin(["sold", "captain"]))])
        team_spending[team] = {
            "spent": int(spent), 
            "remaining": TEAM_BUDGET - int(spent),
            "players": players
        }
    
    progress = {
        "current": sequential_auction["current_index"] + 1,
        "total": len(sequential_auction["player_sequence"])
    }
    team_limits = None
    next_bid = None
    if current_player:
        team_limits = compute_team_limits(
            df,
            current_player,
            current_auction.get("current_bid", 0),
            current_team=current_auction.get("current_team", ""),
        )
        next_bid = get_next_required_bid(
            current_auction.get("current_bid", 0),
            current_player.get("base_price", 0),
            bool(current_auction.get("current_team")),
        )
    
    return render_template("sequential_auction.html", 
                         current_player=current_player, 
                         auction_state=current_auction,
                         team_budgets=team_spending,
                         teams=TEAMS,
                         progress=progress,
                         starting_team=compute_starting_team(),
                         team_limits=team_limits,
                         next_bid=next_bid)

@app.route("/next-player", methods=["POST"])
def next_player():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    if not sequential_auction["active"]:
        flash("No sequential auction in progress!", "error")
        return redirect(url_for("auction"))
    
    # Move to next player
    sequential_auction["current_index"] += 1
    
    if sequential_auction["current_index"] >= len(sequential_auction["player_sequence"]):
        # End of round - if unsold players remain, start another round
        df = load_players()
        unsold_players = df[(df["status"].astype(str).str.lower() == "unsold")]
        if len(unsold_players) > 0:
            sequential_auction["current_index"] = 0
            sequential_auction["player_sequence"] = unsold_players["player_id"].tolist()
            next_player_id = sequential_auction["player_sequence"][0]
            current_auction["player_id"] = next_player_id
            current_auction["current_bid"] = BASE_PRICE
            current_auction["current_team"] = ""
            current_auction["status"] = "bidding"
            broadcast_state()
            flash("New round started for remaining unsold players.", "info")
            return redirect(url_for("sequential_auction_page"))
        # Auction complete
        sequential_auction["active"] = False
        current_auction["player_id"] = None
        current_auction["status"] = "waiting"
        broadcast_state()
        flash("Sequential auction completed! All players processed.", "success")
        return redirect(url_for("auction"))
    
    # Set next player
    next_player_id = sequential_auction["player_sequence"][sequential_auction["current_index"]]
    current_auction["player_id"] = next_player_id
    current_auction["current_bid"] = BASE_PRICE
    current_auction["current_team"] = ""
    current_auction["status"] = "bidding"
    broadcast_state()
    
    flash("Next player loaded!", "info")
    return redirect(url_for("sequential_auction_page"))

@app.route("/reset-captains", methods=["POST"])
def reset_captains():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    # Reset captains to unsold players
    captain_mask = df["status"] == "captain"
    df.loc[captain_mask, "status"] = "unsold"
    df.loc[captain_mask, "team"] = ""
    df.loc[captain_mask, "sold_price"] = 0
    df.loc[captain_mask, "sold_at"] = ""
    save_players(df)
    broadcast_state()
    
    flash("All captains reset to unsold players.", "success")
    return redirect(url_for("auction"))

@app.route("/reset", methods=["POST"])
def reset_auction():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    # Reset CSV data
    df = load_players()
    # Reset only sold players, preserve captains
    sold_mask = df["status"] == "sold"
    df.loc[sold_mask, "status"] = "unsold"
    df.loc[sold_mask, "team"] = ""
    df.loc[sold_mask, "sold_price"] = 0
    df.loc[sold_mask, "sold_at"] = ""
    save_players(df)
    
    # Reset live auction state
    current_auction["player_id"] = None
    current_auction["current_bid"] = 0
    current_auction["current_team"] = ""
    current_auction["status"] = "waiting"
    broadcast_state()
    broadcast_state()
    bump_auction_version()
    
    flash("Auction reset successfully! All players marked as unsold.", "success")
    return redirect(url_for("auction"))

@app.route("/set-captain", methods=["POST"])
def set_captain():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    player_id = int(request.form.get("player_id"))
    team = request.form.get("team")
    
    df = load_players()
    
    # Check if team already has a captain
    existing_captain = df[(df["team"] == team) & (df["status"] == "captain")]
    if len(existing_captain) > 0:
        flash(f"{team} already has a captain: {existing_captain.iloc[0]['name']}", "warning")
        return redirect(url_for("auction"))
    
    # Set new captain
    idx = df.index[df["player_id"] == player_id]
    if len(idx) == 0:
        flash("Player not found.", "error")
    else:
        i = idx[0]
        player_name = df.at[i, "name"]
        df.at[i, "team"] = team
        df.at[i, "status"] = "captain"
        df.at[i, "sold_price"] = 0
        df.at[i, "sold_at"] = ""
        save_players(df)
        broadcast_state()
        flash(f"Set {player_name} as captain of {team}", "success")
    
    return redirect(url_for("auction"))

@app.route("/reset-player/<int:player_id>", methods=["POST"])
def reset_player(player_id):
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    idx = df.index[df["player_id"] == player_id]
    if len(idx) == 0:
        flash("Player not found.", "error")
    else:
        i = idx[0]
        player_name = df.at[i, "name"]
        df.at[i, "status"] = "unsold"
        df.at[i, "team"] = ""
        df.at[i, "sold_price"] = 0
        df.at[i, "sold_at"] = ""
        save_players(df)
        
        # Reset live auction if this player was being auctioned
        if current_auction["player_id"] == player_id:
            current_auction["player_id"] = None
            current_auction["current_bid"] = 0
            current_auction["current_team"] = ""
            current_auction["status"] = "waiting"
            broadcast_state()
            bump_auction_version()
        
        flash(f"Reset {player_name} - marked as unsold.", "info")
    
    return redirect(url_for("auction"))

@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    flash("Logged out successfully", "info")
    return redirect(url_for("index"))

@app.route("/player-management")
def player_management():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    players = df.to_dict(orient="records")
    return render_template("player_management.html", players=players)

@app.route("/upload-players", methods=["POST"])
def upload_players():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    if 'csv_file' not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("player_management"))
    
    file = request.files['csv_file']
    if file.filename == '':
        flash("No file selected", "error")
        return redirect(url_for("player_management"))
    
    try:
        # Read uploaded CSV
        df = pd.read_csv(file)
        
        # Validate required columns
        required_cols = ['name', 'role', 'base_price']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            flash(f"Missing required columns: {', '.join(missing_cols)}", "error")
            return redirect(url_for("player_management"))
        
        # Add missing columns with defaults
        if 'player_id' not in df.columns:
            df['player_id'] = range(1, len(df) + 1)
        if 'age' not in df.columns:
            df['age'] = ''
        if 'batting_style' not in df.columns:
            df['batting_style'] = ''
        if 'bowling_style' not in df.columns:
            df['bowling_style'] = ''
        if 'team' not in df.columns:
            df['team'] = ''
        if 'status' not in df.columns:
            df['status'] = 'unsold'
        if 'sold_price' not in df.columns:
            df['sold_price'] = 0
        if 'sold_at' not in df.columns:
            df['sold_at'] = ''
        
        # Save to CSV
        save_players(df)
        flash(f"Successfully uploaded {len(df)} players", "success")
        
    except Exception as e:
        flash(f"Error processing CSV: {str(e)}", "error")
    
    return redirect(url_for("player_management"))

@app.route("/add-player", methods=["POST"])
def add_player():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    
    # Get next player ID
    next_id = df['player_id'].max() + 1 if not df.empty else 1
    
    # Calculate base price from value + unit
    base_price_value = float(request.form.get('base_price_value'))
    base_price_unit = request.form.get('base_price_unit')
    base_price = int(base_price_value * 10000000) if base_price_unit == 'crore' else int(base_price_value * 100000)
    
    # Create new player
    new_player = {
        'player_id': next_id,
        'name': request.form.get('name'),
        'role': request.form.get('role'),
        'base_price': base_price,
        'age': request.form.get('age') or '',
        'batting_style': request.form.get('batting_style') or '',
        'bowling_style': request.form.get('bowling_style') or '',
        'team': '',
        'status': 'unsold',
        'sold_price': 0,
        'sold_at': '',
        'photo': ''
    }
    
    # Add to dataframe
    df = pd.concat([df, pd.DataFrame([new_player])], ignore_index=True)
    save_players(df)
    
    flash(f"Added player: {new_player['name']}", "success")
    return redirect(url_for("player_management"))

@app.route("/update-player", methods=["POST"])
def update_player():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    player_id = int(request.form.get('player_id'))
    field = request.form.get('field')
    value = request.form.get('value')
    
    df = load_players()
    idx = df.index[df['player_id'] == player_id]
    
    if len(idx) > 0:
        if field == 'base_price':
            value = int(value)
        df.at[idx[0], field] = value
        save_players(df)
        flash(f"Updated {field} for player ID {player_id}", "success")
    
    return redirect(url_for("player_management"))

@app.route("/delete-player", methods=["POST"])
def delete_player():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    player_id = int(request.form.get('player_id'))
    df = load_players()
    
    # Remove player
    df = df[df['player_id'] != player_id]
    save_players(df)
    
    flash(f"Deleted player ID {player_id}", "info")
    return redirect(url_for("player_management"))

@app.route("/reset-all-players", methods=["POST"])
def reset_all_players():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    
    # Reset all players to unsold
    df['team'] = ''
    df['status'] = 'unsold'
    df['sold_price'] = 0
    df['sold_at'] = ''
    
    save_players(df)
    flash("Reset all players to unsold status", "info")
    return redirect(url_for("player_management"))

@app.route("/download-template")
def download_template():
    # Create sample CSV template
    template_data = {
        'name': ['Sample Player 1', 'Sample Player 2', 'Sample Player 3'],
        'role': ['Batsman', 'Bowler', 'All-Rounder'],
        'base_price': [5000000, 5000000, 5000000],
        'age': [25, 28, 30],
        'batting_style': ['Right-hand Bat', 'Right-hand Bat', 'Left-hand Bat'],
        'bowling_style': ['', 'Right-arm Fast', 'Right-arm Off']
    }
    
    df = pd.DataFrame(template_data)
    
    # Create CSV in memory
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    # Convert to bytes
    csv_bytes = io.BytesIO()
    csv_bytes.write(output.getvalue().encode('utf-8'))
    csv_bytes.seek(0)
    
    return send_file(csv_bytes, mimetype='text/csv', as_attachment=True, download_name='player_template.csv')

@app.route("/export-players")
def export_players():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    df = load_players()
    
    # Create CSV in memory
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    # Convert to bytes
    csv_bytes = io.BytesIO()
    csv_bytes.write(output.getvalue().encode('utf-8'))
    csv_bytes.seek(0)
    
    return send_file(csv_bytes, mimetype='text/csv', as_attachment=True, download_name='players_export.csv')

@app.route("/upload-player-photo", methods=["POST"])
def upload_player_photo():
    from flask import jsonify
    
    # Check admin access
    if not session.get("is_admin"):
        return jsonify({"success": False, "error": "Unauthorized"})
    
    if 'photo' not in request.files:
        return jsonify({"success": False, "error": "No file selected"})
    
    file = request.files['photo']
    player_id = request.form.get('player_id')
    
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})
    
    try:
        # Check file size (max 5MB)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > 5 * 1024 * 1024:  # 5MB limit
            return jsonify({"success": False, "error": "File too large. Max 5MB allowed."})
        
        # Open and resize image
        image = Image.open(file)
        
        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        
        # Resize to 200x200 maintaining aspect ratio
        image.thumbnail((200, 200), RESAMPLE_LANCZOS)
        
        # Create square image with padding if needed
        if image.size != (200, 200):
            new_image = Image.new('RGB', (200, 200), (71, 85, 105))  # Gray background
            paste_x = (200 - image.size[0]) // 2
            paste_y = (200 - image.size[1]) // 2
            new_image.paste(image, (paste_x, paste_y))
            image = new_image
        
        # Save resized image
        filename = f"player_{player_id}.jpg"
        file_path = os.path.join(app.static_folder, 'players', filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        image.save(file_path, 'JPEG', quality=85, optimize=True)
        print(f"DEBUG: Saved photo to {file_path}, file exists: {os.path.exists(file_path)}")
        
        # Update player record with photo filename
        df = load_players()
        idx = df.index[df['player_id'] == int(player_id)]
        if len(idx) > 0:
            df.at[idx[0], 'photo'] = filename
            save_players(df)
        
        return jsonify({"success": True, "timestamp": int(time.time())})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/tournament-settings")
def tournament_settings():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    config = load_config()
    return render_template("tournament_settings.html", config=config)

@app.route("/update-tournament-info", methods=["POST"])
def update_tournament_info():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    config = load_config()
    config["tournament"]["name"] = request.form.get("tournament_name")
    config["auction"]["currency"] = request.form.get("currency")
    save_config(config)
    
    # Update global variables
    global CONFIG
    CONFIG = config
    
    flash("Tournament information updated", "success")
    return redirect(url_for("tournament_settings"))

@app.route("/upload-logo", methods=["POST"])
def upload_logo():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    if 'logo_file' not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("tournament_settings"))
    
    file = request.files['logo_file']
    if file.filename == '':
        flash("No file selected", "error")
        return redirect(url_for("tournament_settings"))
    
    # Save logo file
    filename = secure_filename("logo.png")  # Always save as logo.png
    file.save(os.path.join(app.static_folder, filename))
    
    flash("Logo updated successfully", "success")
    return redirect(url_for("tournament_settings"))

@app.route("/update-teams", methods=["POST"])
def update_teams():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    config = load_config()
    
    # Get team names
    team_names = []
    i = 0
    while f"team_{i}" in request.form:
        team_name = request.form.get(f"team_{i}").strip()
        if team_name:
            team_names.append(team_name)
        i += 1
    
    if len(team_names) < 2:
        flash("At least 2 teams required", "error")
        return redirect(url_for("tournament_settings"))
    
    # Calculate budget from value + unit
    budget_value = float(request.form.get("budget_value"))
    budget_unit = request.form.get("budget_unit")
    budget = int(budget_value * 10000000) if budget_unit == "crore" else int(budget_value * 100000)
    
    config["teams"]["names"] = team_names
    config["teams"]["count"] = len(team_names)
    config["teams"]["budget"] = budget
    config["teams"]["min_players"] = int(request.form.get("min_players"))
    config["teams"]["max_players"] = int(request.form.get("max_players"))
    
    save_config(config)
    
    # Update global variables
    global CONFIG, TEAMS, TEAM_BUDGET
    CONFIG = config
    TEAMS = config["teams"]["names"]
    TEAM_BUDGET = config["teams"]["budget"]
    
    flash("Team settings updated", "success")
    return redirect(url_for("tournament_settings"))

@app.route("/update-auction-rules", methods=["POST"])
def update_auction_rules():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    config = load_config()
    
    # Calculate base price from value + unit
    base_price_value = float(request.form.get("base_price_value"))
    base_price_unit = request.form.get("base_price_unit")
    base_price = int(base_price_value * 10000000) if base_price_unit == "crore" else int(base_price_value * 100000)
    
    # Calculate increments from value + unit
    increments = []
    for i in range(1, 4):
        value = float(request.form.get(f"increment_{i}_value"))
        unit = request.form.get(f"increment_{i}_unit")
        increment = int(value * 10000000) if unit == "crore" else int(value * 100000)
        increments.append(increment)
    
    config["auction"]["base_price"] = base_price
    config["auction"]["increments"] = increments
    
    save_config(config)
    
    # Update global variables
    global CONFIG, BASE_PRICE
    CONFIG = config
    BASE_PRICE = config["auction"]["base_price"]
    
    flash("Auction rules updated", "success")
    return redirect(url_for("tournament_settings"))

@app.route("/reset-config", methods=["POST"])
def reset_config():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    # Reset to default config
    default_config = {
        "tournament": {"name": "Palace Premier League", "logo": "logo.png"},
        "teams": {"count": 3, "names": ["Palace Tuskers", "Palace Titans", "Palace Warriors"], "budget": 25000000, "min_players": 8, "max_players": 9},
        "auction": {"base_price": 5000000, "currency": "₹", "increments": [1000000, 2500000, 5000000]}
    }
    
    save_config(default_config)
    
    # Update global variables
    global CONFIG, TEAMS, TEAM_BUDGET, BASE_PRICE
    CONFIG = default_config
    TEAMS = default_config["teams"]["names"]
    TEAM_BUDGET = default_config["teams"]["budget"]
    BASE_PRICE = default_config["auction"]["base_price"]
    
    flash("Settings reset to defaults", "info")
    return redirect(url_for("tournament_settings"))

@app.route("/export-config")
def export_config():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    config = load_config()
    
    # Create JSON in memory
    output = io.StringIO()
    json.dump(config, output, indent=2)
    output.seek(0)
    
    # Convert to bytes
    json_bytes = io.BytesIO()
    json_bytes.write(output.getvalue().encode('utf-8'))
    json_bytes.seek(0)
    
    return send_file(json_bytes, mimetype='application/json', as_attachment=True, download_name='tournament_config.json')

@app.route('/player-card/<int:player_id>.png')
def player_card(player_id):
    df = load_players()
    row = df[df['player_id'] == player_id]
    if row.empty:
        return jsonify({"error": "Player not found"}), 404
    p = row.iloc[0].to_dict()

    # Card dimensions
    W, H = 1400, 720
    bg_color = (17, 24, 39)      # #111827
    panel_color = (2, 6, 23)     # darker
    text_primary = (226, 232, 240)  # #e2e8f0
    text_muted = (148, 163, 184)    # #94a3b8
    accent_blue = (147, 197, 253)   # #93c5fd
    green = (16, 185, 129)          # #10b981
    orange = (245, 158, 11)         # #f59e0b

    # Create image
    img = Image.new('RGB', (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    # Try fonts
    def load_font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return None
    font_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    font_title = None
    font_sub = None
    for fp in font_paths:
        if not font_title:
            font_title = load_font(fp, 64)
        if not font_sub:
            font_sub = load_font(fp, 36)
    if not font_title:
        font_title = ImageFont.load_default()
    if not font_sub:
        font_sub = ImageFont.load_default()

    # Header: tournament name and logo
    tour_name = CONFIG.get('tournament', {}).get('name', 'Tournament')
    draw.text((40, 30), tour_name, fill=text_muted, font=font_sub)
    # Logo (optional, top-right)
    try:
        logo_path = os.path.join(app.static_folder, CONFIG.get('tournament', {}).get('logo', 'logo.png'))
        logo = Image.open(logo_path).convert('RGBA')
        # scale logo
        max_side = 120
        ratio = min(max_side / logo.width, max_side / logo.height)
        logo = logo.resize((int(logo.width * ratio), int(logo.height * ratio)), RESAMPLE_LANCZOS)
        img.paste(logo, (W - logo.width - 40, 20), logo)
    except Exception:
        pass

    # Player photo
    photo_name = p.get('photo') or 'default.png'
    photo_path = os.path.join(app.static_folder, 'players', photo_name)
    try:
        ph = Image.open(photo_path).convert('RGB')
    except Exception:
        ph = Image.new('RGB', (480, 480), panel_color)
    # Center-crop to square, then resize to 480x480
    w, h = ph.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    ph = ph.crop((left, top, left + side, top + side))
    ph = ph.resize((480, 480), RESAMPLE_LANCZOS)
    # Make perfect circular mask
    mask = Image.new('L', (480, 480), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse((0, 0, 480, 480), fill=255)
    px, py = 60, 120
    # Photo border circle
    border = Image.new('RGB', (480 + 12, 480 + 12), accent_blue)
    border_mask = Image.new('L', (480 + 12, 480 + 12), 0)
    ImageDraw.Draw(border_mask).ellipse((0, 0, 480 + 12, 480 + 12), fill=255)
    img.paste(border, (px - 6, py - 6), border_mask)
    img.paste(ph, (px, py), mask)

    # Right panel texts
    name = str(p.get('name') or '')
    role = str(p.get('role') or '-')
    team = str(p.get('team') or '-')
    status = str(p.get('status') or '').lower()
    sold_price = int(p.get('sold_price') or 0)

    # Name
    name_x, name_y = 600, 150
    draw.text((name_x, name_y), name, fill=text_primary, font=font_title)
    # Role
    draw.text((name_x, name_y + 80), role, fill=text_muted, font=font_sub)
    # Team
    draw.text((name_x, name_y + 140), f"Team: {team}", fill=text_primary, font=font_sub)

    # Price / Captain label
    if status == 'captain':
        draw.text((name_x, name_y + 210), 'Captain', fill=orange, font=font_sub)
    elif status == 'sold':
        price_str = f"Sold for ₹{format_indian_currency(sold_price)}"
        draw.text((name_x, name_y + 210), price_str, fill=green, font=font_sub)
    else:
        base_price = int(p.get('base_price') or 0)
        price_str = f"Base: ₹{format_indian_currency(base_price)}"
        draw.text((name_x, name_y + 210), price_str, fill=text_muted, font=font_sub)

    # Footer bar
    draw.rectangle([(0, H-60), (W, H)], fill=panel_color)
    draw.text((40, H-50), f"Player ID: {p.get('player_id')}", fill=text_muted, font=font_sub)

    # Return as download
    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    fname = f"player_{p.get('player_id')}_card.png"
    return send_file(bio, mimetype='image/png', as_attachment=True, download_name=fname)

@app.route('/team-card/<path:team_name>.png')
def team_card(team_name):
    df = load_players()
    team_df = df[df['team'] == team_name]
    if team_df.empty and team_name not in TEAMS:
        return jsonify({"error": "Team not found"}), 404
    # Sort captain first, then name
    team_df = team_df.copy()
    team_df['status'] = team_df['status'].astype(str)
    team_df.sort_values(by=['status','name'], key=lambda s: s.map(lambda v: 0 if str(v).lower()== 'captain' else 1), inplace=True)

    spent = pd.to_numeric(team_df['sold_price'], errors='coerce').fillna(0).sum()
    count = len(team_df)
    remaining = TEAM_BUDGET - int(spent)

    # Layout sizing
    W = 1400
    header_h = 180
    row_h = 60
    rows = max(1, len(team_df))
    H = header_h + rows*row_h + 80
    bg = (17,24,39)
    panel = (30,41,59)
    text = (226,232,240)
    muted = (148,163,184)
    green = (16,185,129)
    orange = (245,158,11)

    img = Image.new('RGB', (W, H), bg)
    draw = ImageDraw.Draw(img)

    # Fonts
    def load_font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return None
    font_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ]
    f_title = None; f_sub = None
    for fp in font_paths:
        if not f_title:
            f_title = load_font(fp, 54)
        if not f_sub:
            f_sub = load_font(fp, 30)
    f_title = f_title or ImageFont.load_default()
    f_sub = f_sub or ImageFont.load_default()

    # Header
    draw.text((40, 30), CONFIG.get('tournament',{}).get('name','Tournament'), fill=muted, font=f_sub)
    # Team name and counts on right
    draw.text((40, 90), team_name, fill=text, font=f_title)
    stats = f"{count} players   |   Spent: ₹{format_indian_currency(int(spent))}   |   Remaining: ₹{format_indian_currency(int(remaining))}"
    draw.text((40, 150), stats, fill=muted, font=f_sub)

    # Table headers
    y = header_h
    x_name, x_role, x_price = 40, 620, 980
    draw.text((x_name, y), 'Name', fill=muted, font=f_sub)
    draw.text((x_role, y), 'Category', fill=muted, font=f_sub)
    draw.text((x_price, y), 'Price', fill=muted, font=f_sub)
    y += 20
    draw.line([(40,y),(W-40,y)], fill=panel, width=2)
    y += 20

    # Rows
    for _, r in team_df.iterrows():
        name = str(r.get('name') or '-')
        role = str(r.get('role') or '-')
        status = str(r.get('status') or '').lower()
        sold_price = int(r.get('sold_price') or 0)
        draw.text((x_name, y), name, fill=text, font=f_sub)
        draw.text((x_role, y), role, fill=muted, font=f_sub)
        if status == 'captain':
            draw.text((x_price, y), 'Captain', fill=orange, font=f_sub)
        else:
            pr = '-' if sold_price == 0 else f"₹{format_indian_currency(sold_price)}"
            draw.text((x_price, y), pr, fill=green if sold_price else muted, font=f_sub)
        y += row_h

    bio = io.BytesIO()
    img.save(bio, format='PNG')
    bio.seek(0)
    safe_team = team_name.lower().replace(' ','_')
    return send_file(bio, mimetype='image/png', as_attachment=True, download_name=f"{safe_team}_card.png")

@app.route("/live-version")
def live_version():
    # Lightweight endpoint to let public live view detect updates without full reload
    from flask import make_response
    resp = jsonify({"version": auction_version})
    # Prevent caching
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp

@app.route('/events')
def events():
    # Server-Sent Events stream for public viewers
    q = _subscribe_sse()

    @stream_with_context
    def gen():
        heartbeat_sec = 15  # must be < gunicorn timeout
        try:
            # Send an initial state so clients can sync immediately
            init_msg = json.dumps({"type": "state", "version": auction_version, "payload": build_live_payload()})
            yield f"data: {init_msg}\n\n"
            while True:
                try:
                    # Wait for broadcast, but wake up periodically to send heartbeat
                    msg = q.get(timeout=heartbeat_sec)
                    if isinstance(msg, str):
                        yield f"data: {msg}\n\n"
                    else:
                        wrapped = json.dumps({"type": "state", "version": auction_version, "payload": build_live_payload()})
                        yield f"data: {wrapped}\n\n"
                except queue.Empty:
                    # Heartbeat to keep connection and workers alive
                    # SSE comment line is ignored by clients but keeps the stream active
                    yield f": keep-alive {int(time.time())}\n\n"
        except (GeneratorExit, BrokenPipeError, ConnectionAbortedError):
            # Client disconnected
            pass
        finally:
            _unsubscribe_sse(q)

    headers = {
        'Cache-Control': 'no-cache',
        'Content-Type': 'text/event-stream',
        'X-Accel-Buffering': 'no',  # for nginx
        'Connection': 'keep-alive',
    }
    return Response(gen(), headers=headers, mimetype='text/event-stream')

@app.route("/import-config", methods=["POST"])
def import_config():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    if 'config_file' not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("tournament_settings"))
    
    file = request.files['config_file']
    if file.filename == '':
        flash("No file selected", "error")
        return redirect(url_for("tournament_settings"))
    
    try:
        config = json.load(file)
        save_config(config)
        
        # Update global variables
        global CONFIG, TEAMS, TEAM_BUDGET, BASE_PRICE
        CONFIG = config
        TEAMS = config["teams"]["names"]
        TEAM_BUDGET = config["teams"]["budget"]
        BASE_PRICE = config["auction"]["base_price"]
        
        flash("Configuration imported successfully", "success")
    except Exception as e:
        flash(f"Error importing config: {str(e)}", "error")
    
    return redirect(url_for("tournament_settings"))

if __name__ == "__main__":
    app.run(debug=True)
