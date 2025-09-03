
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
import pandas as pd
from datetime import datetime
import os
import json
from werkzeug.utils import secure_filename
import io
from PIL import Image

app = Flask(__name__)
app.secret_key = "change-me"

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
        if crores == int(crores):
            return f"{int(crores)}Cr"
        else:
            return f"{crores:.1f}Cr"
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

DATA_FILE = os.path.join(os.path.dirname(__file__), "players.csv")

def load_players():
    df = pd.read_csv(DATA_FILE)
    # Normalize expected columns / add if missing
    for col in ["team", "status", "sold_price", "sold_at", "photo"]:
        if col not in df.columns:
            df[col] = "" if col in ["team", "sold_at", "photo"] else 0 if col == "sold_price" else "unsold"
    # Ensure player_id is int-like
    if "player_id" in df.columns:
        try:
            df["player_id"] = df["player_id"].astype(int)
        except:
            pass
    # Replace NaN/None with empty string for display
    df = df.fillna('')
    # Save updated CSV with photo column if it was missing
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
                    flash(f"{team} budget exceeded! Remaining: ₹{remaining_budget:,}", "error")
                elif sold_price > max_allowed_bid:
                    flash(f"Max bid allowed: ₹{max_allowed_bid:,} (Need ₹{players_needed_after_this * BASE_PRICE:,} for {players_needed_after_this} more players)", "error")
                else:
                    df.at[i, "team"] = team
                    df.at[i, "status"] = "sold"
                    df.at[i, "sold_price"] = sold_price
                    df.at[i, "sold_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_players(df)
                    flash(f"Sold player #{pid} to {team} for ₹{sold_price:,}.", "success")

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
    return render_template("auction.html", players_unsold=players_unsold, players_sold=players_sold, team_budgets=team_spending, total_budget=TEAM_BUDGET, is_admin=False)

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
            flash(f"Started bidding for {player['name']} at base price ₹{player['base_price']:,}", "info")
            
        elif action == "update_bid":
            new_bid = int(request.form.get("bid_amount"))
            team = request.form.get("team")
            current_auction["current_bid"] = new_bid
            current_auction["current_team"] = team
            current_auction["status"] = "bidding"
            
        elif action == "sold":
            # If no bid placed, sell at base price
            if current_auction["current_bid"] == 0:
                current_auction["current_bid"] = player["base_price"]
                current_auction["current_team"] = request.form.get("team", "")
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
            
            flash(f"SOLD! {player['name']} to {df.at[idx, 'team']} for ₹{format_indian_currency(df.at[idx, 'sold_price'])}", "success")
            
            # If in sequential auction, move to next player
            if sequential_auction["active"]:
                sequential_auction["current_index"] += 1
                
                if sequential_auction["current_index"] >= len(sequential_auction["player_sequence"]):
                    # Auction complete
                    sequential_auction["active"] = False
                    current_auction["player_id"] = None
                    current_auction["status"] = "waiting"
                    flash("Sequential auction completed! All players processed.", "success")
                    return redirect(url_for("auction"))
                
                # Set next player
                next_player_id = sequential_auction["player_sequence"][sequential_auction["current_index"]]
                current_auction["player_id"] = next_player_id
                current_auction["current_bid"] = BASE_PRICE
                current_auction["current_team"] = ""
                current_auction["status"] = "bidding"
                
                return redirect(url_for("sequential_auction_page"))
            else:
                return redirect(url_for("auction"))
    
    return render_template("live_bidding.html", player=player, auction_state=current_auction, teams=TEAMS)

@app.route("/live-view")
def live_view():
    """Public live view of current bidding"""
    df = load_players()
    current_player = None
    
    if current_auction["player_id"]:
        current_player = df[df["player_id"] == current_auction["player_id"]].iloc[0].to_dict()
    
    return render_template("live_view.html", current_player=current_player, auction_state=current_auction)

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
    
    return render_template("sequential_auction.html", 
                         current_player=current_player, 
                         auction_state=current_auction,
                         team_budgets=team_spending,
                         teams=TEAMS,
                         progress=progress)

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
        # Auction complete
        sequential_auction["active"] = False
        current_auction["player_id"] = None
        current_auction["status"] = "waiting"
        flash("Sequential auction completed! All players processed.", "success")
        return redirect(url_for("auction"))
    
    # Set next player
    next_player_id = sequential_auction["player_sequence"][sequential_auction["current_index"]]
    current_auction["player_id"] = next_player_id
    current_auction["current_bid"] = BASE_PRICE
    current_auction["current_team"] = ""
    current_auction["status"] = "bidding"
    
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
        image.thumbnail((200, 200), Image.Resampling.LANCZOS)
        
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
