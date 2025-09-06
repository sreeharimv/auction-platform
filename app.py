
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
import sqlite3

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
    "status": "waiting",  # waiting, bidding, going, sold
    "announcement": None,
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
        "next_bid": None,
        "announcement": current_auction.get("announcement"),
        "player_sold": current_auction.get("player_sold", False),
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
            # If already sold, don't show eligible bidders
            if (current_auction.get("status") or "").lower() != "sold":
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
                # Calculate next required bid
                payload["next_bid"] = get_next_required_bid(
                    current_auction.get("current_bid", 0),
                    p.get("base_price", 0),
                    bool(current_auction.get("current_team")),
                )
    return payload

def broadcast_state():
    """Increment version and push a JSON state payload to SSE listeners."""
    global auction_version, _sse_clients, _sse_lock
    auction_version += 1
    message = json.dumps({
        "type": "state",
        "version": auction_version,
        "payload": build_live_payload(),
    })
    with _sse_lock:
        dead_clients = set()
        for q in list(_sse_clients):
            try:
                q.put_nowait(message)
            except Exception:
                dead_clients.add(q)
        # Remove dead clients
        _sse_clients -= dead_clients

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
    team_budget = CONFIG["teams"]["budget"]
    base_price_rule = CONFIG["auction"]["base_price"]
    max_players_allowed = CONFIG["teams"].get("max_players", 9)

    # Determine next required bids relative to current auction state
    effective_current = current_bid or 0
    no_leading_bid = (not current_team)
    # Precompute aggregates for all teams
    df_status = df.get("status", pd.Series(dtype=str)).astype(str).str.lower()
    df_team = df.get("team", pd.Series(dtype=str))
    sold_prices = pd.to_numeric(df.get("sold_price", pd.Series(dtype=float)), errors="coerce").fillna(0)
    spent_by_team = sold_prices.groupby(df_team).sum()
    sold_count_by_team = (df_status == "sold").groupby(df_team).sum()
    captain_count_by_team = (df_status == "captain").groupby(df_team).sum()
    # Last-slot rule: if any team would reach max with this purchase
    last_slot_exists = False
    for team in TEAMS:
        sold_count = int(sold_count_by_team.get(team, 0))
        captain_count = int(captain_count_by_team.get(team, 0))
        if sold_count + captain_count == max_players_allowed - 1:
            last_slot_exists = True
            break

    if effective_current <= player["base_price"] and no_leading_bid:
        # First bid can be at base price
        min_next_bid = player["base_price"]
        # For second next bid, depend on rule
        step = CONFIG["auction"]["increments"][0] if last_slot_exists else (
            CONFIG["auction"]["increments"][0] if player["base_price"] < base_price_rule * 2 else (
                CONFIG["auction"]["increments"][1] if player["base_price"] < base_price_rule * 4 else CONFIG["auction"]["increments"][2]
            )
        )
        second_next_bid = min_next_bid + step if min_next_bid is not None else None
    else:
        # Next price based on increments; allow smallest slab if last-slot rule applies
        if last_slot_exists:
            min_next_bid = effective_current + CONFIG["auction"]["increments"][0]
            second_next_bid = min_next_bid + CONFIG["auction"]["increments"][0]
        else:
            next_prices = [p for p in get_bid_increments(effective_current) if p > effective_current]
            min_next_bid = next_prices[0] if next_prices else None
            second_next_bid = next_prices[1] if len(next_prices) > 1 else None

    team_limits = {}
    for team in TEAMS:
        spent = int(spent_by_team.get(team, 0))
        sold_count = int(sold_count_by_team.get(team, 0))
        captain_count = int(captain_count_by_team.get(team, 0))

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
            if last_slot_exists:
                return val + CONFIG["auction"]["increments"][0]
            if val < base_price_rule * 2:
                return val + CONFIG["auction"]["increments"][0]
            elif val < base_price_rule * 4:
                return val + CONFIG["auction"]["increments"][1]
            else:
                return val + CONFIG["auction"]["increments"][2]

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
    # Last-slot rule: if any team is at max-1 players, use smallest increment
    try:
        df = load_players()
        df_status = df.get("status", pd.Series(dtype=str)).astype(str).str.lower()
        df_team = df.get("team", pd.Series(dtype=str))
        sold_count_by_team = (df_status == "sold").groupby(df_team).sum()
        captain_count_by_team = (df_status == "captain").groupby(df_team).sum()
        max_players_allowed = CONFIG["teams"].get("max_players", 9)
        last_slot_exists = False
        for team in TEAMS:
            sold_c = int(sold_count_by_team.get(team, 0))
            cap_c = int(captain_count_by_team.get(team, 0))
            if sold_c + cap_c == max_players_allowed - 1:
                last_slot_exists = True
                break
        if last_slot_exists:
            return current_bid + CONFIG["auction"]["increments"][0]
    except Exception:
        pass
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

DB_FILE = os.path.join(os.path.dirname(__file__), "players.db")

def init_db():
    """Initialize SQLite database with players table"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            age TEXT,
            role TEXT,
            batting_style TEXT,
            bowling_style TEXT,
            base_price INTEGER,
            team TEXT,
            status TEXT DEFAULT 'unsold',
            sold_price INTEGER DEFAULT 0,
            sold_at TEXT,
            photo TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# Debug database info
print(f"DEBUG: Using database file: {DB_FILE}")
print(f"DEBUG: Database file exists: {os.path.exists(DB_FILE)}")
if os.path.exists(DB_FILE):
    print(f"DEBUG: Database file size: {os.path.getsize(DB_FILE)} bytes")

# Migrate CSV data to SQLite if CSV exists
def migrate_csv_to_db():
    csv_file = os.path.join(os.path.dirname(__file__), "players.csv")
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            if not df.empty:
                conn = sqlite3.connect(DB_FILE)
                # Always migrate from CSV to ensure we're using SQLite
                df.to_sql('players', conn, if_exists='replace', index=False)
                print(f"Migrated {len(df)} players from CSV to SQLite")
                # Remove CSV file after successful migration
                os.remove(csv_file)
                print("Removed CSV file after migration")
                conn.close()
        except Exception as e:
            print(f"CSV migration failed: {e}")
    else:
        print("No CSV file found, using SQLite database")

migrate_csv_to_db()

def load_players():
    """Load players from SQLite database as pandas DataFrame"""
    import time, traceback
    start_time = time.time()
    # Print caller info
    stack = traceback.extract_stack()
    caller = stack[-2]
    print(f"DEBUG: load_players() called from {caller.filename}:{caller.lineno} in {caller.name}()")
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM players ORDER BY player_id", conn)
    conn.close()
    # Replace NaN/None with empty string for display
    df = df.fillna('')
    end_time = time.time()
    print(f"DEBUG: load_players() took {end_time - start_time:.3f} seconds, loaded {len(df)} players")
    return df

def save_players(df):
    """Save players DataFrame to SQLite database"""
    conn = sqlite3.connect(DB_FILE)
    df.to_sql('players', conn, if_exists='replace', index=False)
    conn.close()

def update_player_db(player_id, **kwargs):
    """Update specific player fields - much faster than full save"""
    conn = sqlite3.connect(DB_FILE)
    set_clause = ', '.join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [player_id]
    conn.execute(f"UPDATE players SET {set_clause} WHERE player_id = ?", values)
    conn.commit()
    conn.close()

@app.route("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

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
    import time
    start_time = time.time()
    print(f"DEBUG: Starting players route")
    df = load_players()
    sort = request.args.get("sort", "player_id")
    asc = request.args.get("asc", "1") == "1"
    if sort in df.columns:
        try:
            df = df.sort_values(by=sort, ascending=asc)
        except Exception:
            pass
    players = df.to_dict(orient="records")
    end_time = time.time()
    print(f"DEBUG: players route took {end_time - start_time:.3f} seconds total")
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
                    player_name = df.at[i, 'name']  # Get name before update
                    update_player_db(pid, team=team, status="sold", sold_price=sold_price, sold_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    # Set announcement for public live view and broadcast
                    current_auction["announcement"] = f"SOLD! {player_name} to {team} for ₹{format_indian_currency(sold_price)}"
                    current_auction["player_sold"] = True
                    broadcast_state()
                    flash(f"Sold player #{pid} to {team} for ₹{format_indian_currency(sold_price)}.", "success")

        elif action == "revert":
            idx = df.index[df["player_id"] == pid]
            if len(idx) == 0:
                flash("Player not found.", "error")
                return redirect(url_for("auction"))
            i = idx[0]
            update_player_db(pid, status="unsold", team="", sold_price=0, sold_at="")
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

    # Optional: current live bidding context for quick-bid controls on admin page
    current_player = None
    team_limits = None
    next_bid = None
    if current_auction.get("player_id"):
        row = df[df["player_id"] == current_auction["player_id"]]
        if not row.empty:
            current_player = row.iloc[0].to_dict()
            if (current_auction.get("status") or "").lower() in ("bidding", "going"):
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

    return render_template(
        "auction.html",
        players_unsold=players_unsold,
        players_sold=players_sold,
        team_budgets=team_spending,
        total_budget=TEAM_BUDGET,
        base_price=BASE_PRICE,
        is_admin=True,
        current_player=current_player,
        auction_state=current_auction,
        team_limits=team_limits,
        next_bid=next_bid,
        teams=TEAMS,
    )

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



@app.route("/live-view")
def live_view():
    """Public live view of current bidding"""
    df = load_players()
    current_player = None
    team_limits = None
    starting_team = compute_starting_team()
    if current_auction["player_id"]:
        current_player = df[df["player_id"] == current_auction["player_id"]].iloc[0].to_dict()
        # Only compute team limits if still in bidding/going state
        if (current_auction.get("status") or "").lower() not in ("sold", "waiting"):
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
    
    # Clear any previous announcement and set first player as current
    current_auction["announcement"] = None
    first_player_id = sequential_auction["player_sequence"][0]
    first_player_row = df[df["player_id"] == first_player_id]
    first_player_base_price = int(first_player_row.iloc[0]["base_price"]) if not first_player_row.empty else BASE_PRICE
    current_auction["player_id"] = first_player_id
    current_auction["current_bid"] = first_player_base_price
    current_auction["current_team"] = ""
    current_auction["status"] = "bidding"
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

@app.route("/end-sequential", methods=["POST"])
def end_sequential():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    # End sequential auction
    sequential_auction["active"] = False
    current_auction["player_id"] = None
    current_auction["status"] = "waiting"
    current_auction["announcement"] = None
    broadcast_state()
    
    flash("Sequential auction ended manually.", "info")
    return redirect(url_for("auction"))

@app.route("/next-player", methods=["POST"])
def next_player():
    import time
    start_time = time.time()
    print(f"DEBUG: next_player() called")
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    if not sequential_auction["active"]:
        flash("No sequential auction in progress!", "error")
        return redirect(url_for("auction"))
    
    # Move to next player
    sequential_auction["current_index"] += 1
    
    if sequential_auction["current_index"] >= len(sequential_auction["player_sequence"]):
        # End of round - check if any auctionable players remain
        df = load_players()
        unsold_players = df[(df["status"].astype(str).str.lower() == "unsold")]
        # Check if all auctionable players (excluding captains) are sold
        auctionable_players = df[df["status"].astype(str).str.lower() != "captain"]
        sold_players = auctionable_players[auctionable_players["status"].astype(str).str.lower() == "sold"]
        
        if len(unsold_players) > 0 and len(sold_players) < len(auctionable_players):
            sequential_auction["current_index"] = 0
            sequential_auction["player_sequence"] = unsold_players["player_id"].tolist()
            next_player_id = sequential_auction["player_sequence"][0]
            next_player_row = df[df["player_id"] == next_player_id]
            next_player_base_price = int(next_player_row.iloc[0]["base_price"]) if not next_player_row.empty else BASE_PRICE
            current_auction["player_id"] = next_player_id
            current_auction["current_bid"] = next_player_base_price
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
    
    # Clear any previous announcement and set next player
    current_auction["announcement"] = None
    current_auction["history"] = []  # Clear bid history
    current_auction["player_sold"] = False  # Reset sold flag
    next_player_id = sequential_auction["player_sequence"][sequential_auction["current_index"]]
    df = load_players()
    next_player_row = df[df["player_id"] == next_player_id]
    next_player_base_price = int(next_player_row.iloc[0]["base_price"]) if not next_player_row.empty else BASE_PRICE
    current_auction["player_id"] = next_player_id
    current_auction["current_bid"] = next_player_base_price
    current_auction["current_team"] = ""
    current_auction["status"] = "bidding"
    broadcast_state()
    
    end_time = time.time()
    print(f"DEBUG: next_player() completed in {end_time - start_time:.3f} seconds")
    flash("Next player loaded!", "info")
    return redirect(url_for("sequential_auction_page"))

@app.route("/reset-captains", methods=["POST"])
def reset_captains():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    # Reset captains to unsold players directly in database
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE players SET status = 'unsold', team = '', sold_price = 0, sold_at = '' WHERE status = 'captain'")
    conn.commit()
    conn.close()
    broadcast_state()
    
    flash("All captains reset to unsold players.", "success")
    return redirect(url_for("auction"))

@app.route("/reset", methods=["POST"])
def reset_auction():
    # Check admin access
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    
    # Reset only sold players, preserve captains - direct database operation
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE players SET status = 'unsold', team = '', sold_price = 0, sold_at = '' WHERE status = 'sold'")
    conn.commit()
    conn.close()
    
    # Reset live auction state
    current_auction["player_id"] = None
    current_auction["current_bid"] = 0
    current_auction["current_team"] = ""
    current_auction["status"] = "waiting"
    broadcast_state()
    
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
        update_player_db(player_id, team=team, status="captain", sold_price=0, sold_at="")
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
        update_player_db(player_id, status="unsold", team="", sold_price=0, sold_at="")
        
        # Reset live auction if this player was being auctioned
        if current_auction["player_id"] == player_id:
            current_auction["player_id"] = None
            current_auction["current_bid"] = 0
            current_auction["current_team"] = ""
            current_auction["status"] = "waiting"
            broadcast_state()
        
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
def update_player_route():
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
        # Use direct database update instead of DataFrame
        update_player_db(player_id, **{field: value})
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
    
    # Reset all players to unsold - direct database operation
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE players SET team = '', status = 'unsold', sold_price = 0, sold_at = ''")
    conn.commit()
    conn.close()
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
            # Use direct database update instead of DataFrame
            update_player_db(int(player_id), photo=filename)
        
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

# Removed player-card and team-card endpoints as per requirements

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
        heartbeat_sec = 10  # must be < any proxy/worker timeout
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

# Lightweight APIs for faster admin interactions (no full page reload)
@app.route('/api/bid', methods=['POST'])
def api_bid():
    if not session.get("is_admin"):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        player_id = int(data.get('player_id') or current_auction.get('player_id') or 0)
        team = (data.get('team') or '').strip()
        if not player_id or not team:
            return jsonify({"ok": False, "error": "Missing player_id or team"}), 400
        df = load_players()
        row = df[df['player_id'] == player_id]
        if row.empty:
            return jsonify({"ok": False, "error": "Player not found"}), 404
        player = row.iloc[0].to_dict()
        # Compute next required bid
        has_leader = bool(current_auction.get('current_team'))
        next_bid = get_next_required_bid(current_auction.get('current_bid', 0), player.get('base_price', 0), has_leader)
        if next_bid is None:
            return jsonify({"ok": False, "error": "No higher increments available"}), 400
        # Validate team eligibility
        limits = compute_team_limits(df, player, current_auction.get('current_bid', 0), current_team=current_auction.get('current_team', ''))
        tl = limits.get(team)
        if not tl or not tl.get('can_bid_now'):
            return jsonify({"ok": False, "error": "Team not eligible for next bid"}), 400
        # Apply bid (append to history for undo)
        current_auction.setdefault('history', [])
        current_auction['history'].append({
            'bid': next_bid,
            'team': team,
            'ts': datetime.now().isoformat(),
        })
        current_auction['player_id'] = player_id
        current_auction['current_bid'] = next_bid
        current_auction['current_team'] = team
        current_auction['status'] = 'bidding'
        # Compute next required after applying this bid
        next_required = get_next_required_bid(next_bid, player.get('base_price', 0), True)
        broadcast_state()
        return jsonify({"ok": True, "applied_bid": next_bid, "next_required": next_required, "leader": team, "status": "bidding"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/api/sold', methods=['POST'])
def api_sold():
    if not session.get("is_admin"):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        player_id = int(data.get('player_id') or current_auction.get('player_id') or 0)
        print(f"DEBUG SOLD: player_id={player_id}, current_auction={current_auction}")
        if not player_id:
            return jsonify({"ok": False, "error": "No active player"}), 400
        df = load_players()
        idxs = df.index[df['player_id'] == player_id]
        if len(idxs) == 0:
            return jsonify({"ok": False, "error": "Player not found"}), 404
        idx = idxs[0]
        # Get sale team - if no current team, need to determine which team to sell to
        sale_team = current_auction.get('current_team') or ''
        # Get player info first
        player = df.iloc[idx].to_dict()
        if not sale_team:
            # If no bids placed, we need a team to sell to - use starting team or first eligible team
            starting_team = compute_starting_team()
            if starting_team:
                sale_team = starting_team
                # Set current bid to base price if not set
                if current_auction.get('current_bid', 0) == 0:
                    current_auction['current_bid'] = player.get('base_price', 0)
            else:
                return jsonify({"ok": False, "error": "No team determined for sale"}), 400
        limits = compute_team_limits(df, player, current_auction.get('current_bid', 0), current_team=current_auction.get('current_team', ''))
        tl = limits.get(sale_team)
        if not tl or current_auction.get('current_bid', 0) > tl.get('max_bid', 0):
            return jsonify({"ok": False, "error": "Team cannot complete purchase"}), 400
        # Get player info before updating
        player_name = player['name']
        sold_price = int(current_auction.get('current_bid', 0))
        # Persist sale
        update_player_db(player_id, team=sale_team, status='sold', sold_price=sold_price, sold_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        # Announce and keep SOLD state for viewers
        current_auction['announcement'] = f"SOLD! {player_name} to {sale_team} for ₹{format_indian_currency(sold_price)}"
        current_auction['status'] = 'sold'
        current_auction['player_sold'] = True
        broadcast_state()
        return jsonify({"ok": True})
    except Exception as e:
        print(f"ERROR in api_sold: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route('/api/undo', methods=['POST'])
def api_undo():
    if not session.get("is_admin"):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        player_id = current_auction.get('player_id')
        if not player_id:
            return jsonify({"ok": False, "error": "No active player"}), 400
        df = load_players()
        row = df[df['player_id'] == player_id]
        if row.empty:
            return jsonify({"ok": False, "error": "Player not found"}), 404
        base_price = int(row.iloc[0].get('base_price') or 0)
        hist = current_auction.get('history') or []
        if not hist:
            # Reset to base with no leader
            current_auction['current_bid'] = base_price
            current_auction['current_team'] = ''
            current_auction['status'] = 'bidding'
            broadcast_state()
            return jsonify({"ok": True, "current_bid": base_price, "leader": ""})
        # Pop last bid
        hist.pop()
        if hist:
            last = hist[-1]
            current_auction['current_bid'] = int(last.get('bid') or base_price)
            current_auction['current_team'] = last.get('team') or ''
        else:
            current_auction['current_bid'] = base_price
            current_auction['current_team'] = ''
        current_auction['status'] = 'bidding'
        broadcast_state()
        return jsonify({"ok": True, "current_bid": current_auction['current_bid'], "leader": current_auction['current_team']})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
