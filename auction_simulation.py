import random

# Player data with ratings
players = {
    "Sreekanth": 92, "Sreehari": 93, "Sidharth": 85, "Kannan": 50, "Appu": 90,
    "Ashith": 65, "Marsh": 92, "Hari": 91, "Unnikrishnan": 60, "Sabarish": 85,
    "Raj Narayanan": 65, "Govind M": 90, "Renjith": 75, "Nandu": 90, "Penakkan": 85,
    "Raman Mpilly": 65, "Arjun": 90, "Arun Kasi": 90, "Arjun M": 75, "Arun Chandran": 65,
    "Ramkumar": 50, "Abhilash": 85, "Vysakh": 75, "Vedu": 75, "Ram Manohar": 90, "Kiran": 90
}

# Team setup
teams = {
    "Palace Tuskers": {"budget": 35, "players": [], "captain": None},
    "Palace Titans": {"budget": 35, "players": [], "captain": None}, 
    "Palace Warriors": {"budget": 35, "players": [], "captain": None}
}

BASE_PRICE = 0.5  # 50L in Crores

def get_bid_amount(rating, team_budget, players_needed):
    """Simulate realistic bidding based on player rating and team situation"""
    if rating >= 90:  # Premium players
        return min(random.uniform(3, 8), team_budget - (players_needed * BASE_PRICE))
    elif rating >= 80:  # Good players  
        return min(random.uniform(1.5, 4), team_budget - (players_needed * BASE_PRICE))
    elif rating >= 65:  # Average players
        return min(random.uniform(0.5, 2), team_budget - (players_needed * BASE_PRICE))
    else:  # Low rated players
        return BASE_PRICE

def simulate_auction():
    print("=== AUCTION SIMULATION ===\n")
    
    # Set captains (highest rated players)
    captains = ["Sreehari", "Sreekanth", "Marsh"]  # Top 3 players
    team_names = list(teams.keys())
    
    for i, captain in enumerate(captains):
        teams[team_names[i]]["captain"] = captain
        teams[team_names[i]]["players"].append(captain)
        print(f"{team_names[i]} Captain: {captain} ({players[captain]} rating)")
    
    # Remove captains from auction pool
    auction_players = {k: v for k, v in players.items() if k not in captains}
    
    # Sort players by rating (auction order - highest first)
    sorted_players = sorted(auction_players.items(), key=lambda x: x[1], reverse=True)
    
    print(f"\n=== AUCTION START ===")
    print(f"Players to auction: {len(sorted_players)}")
    
    for player_name, rating in sorted_players:
        print(f"\n--- {player_name} (Rating: {rating}) ---")
        
        # Check which teams can bid
        eligible_teams = []
        for team_name, team_data in teams.items():
            current_players = len(team_data["players"])
            if current_players < 9:  # Max 9 players per team
                players_needed = max(0, 8 - current_players - 1)  # After this purchase
                max_bid = team_data["budget"] - (players_needed * BASE_PRICE)
                if max_bid >= BASE_PRICE:
                    eligible_teams.append((team_name, max_bid))
        
        if not eligible_teams:
            print(f"❌ {player_name} - No teams can afford!")
            continue
            
        # Simulate bidding
        bids = []
        for team_name, max_bid in eligible_teams:
            # Teams more likely to bid on higher rated players
            bid_probability = min(0.9, rating / 100 + 0.2)
            if random.random() < bid_probability:
                bid_amount = get_bid_amount(rating, max_bid, max(0, 8 - len(teams[team_name]["players"]) - 1))
                if bid_amount >= BASE_PRICE and bid_amount <= max_bid:
                    bids.append((team_name, bid_amount))
        
        if bids:
            # Highest bidder wins
            winner, winning_bid = max(bids, key=lambda x: x[1])
            teams[winner]["players"].append(player_name)
            teams[winner]["budget"] -= winning_bid
            print(f"✅ SOLD to {winner} for ₹{winning_bid:.1f}Cr")
        else:
            print(f"❌ {player_name} - No bids (teams being selective)")
    
    # Show final results
    print(f"\n=== FINAL RESULTS ===")
    total_players_assigned = 0
    for team_name, team_data in teams.items():
        print(f"\n{team_name}:")
        print(f"  Players: {len(team_data['players'])}")
        print(f"  Budget left: ₹{team_data['budget']:.1f}Cr")
        print(f"  Squad: {', '.join(team_data['players'])}")
        total_players_assigned += len(team_data["players"])
    
    unsold_players = [name for name in players.keys() if not any(name in team["players"] for team in teams.values())]
    print(f"\n❌ UNSOLD PLAYERS ({len(unsold_players)}):")
    for player in unsold_players:
        print(f"  {player} (Rating: {players[player]})")
    
    print(f"\nTotal players assigned: {total_players_assigned}/26")
    return unsold_players

if __name__ == "__main__":
    unsold = simulate_auction()
    
    if unsold:
        print(f"\n=== AUTO-ASSIGNMENT (Highest Purse Rule) ===")
        
        for player in unsold:
            # Find teams with space and their remaining budgets
            eligible_teams = []
            for team_name, team_data in teams.items():
                space = 9 - len(team_data["players"])
                if space > 0 and team_data["budget"] >= BASE_PRICE:
                    eligible_teams.append((team_name, team_data["budget"]))
            
            if eligible_teams:
                # Assign to team with highest remaining budget
                winner_team, highest_budget = max(eligible_teams, key=lambda x: x[1])
                teams[winner_team]["players"].append(player)
                teams[winner_team]["budget"] -= BASE_PRICE
                print(f"✅ {player} auto-assigned to {winner_team} (₹{highest_budget:.1f}Cr budget) for ₹{BASE_PRICE}Cr")
            else:
                print(f"❌ {player} - No eligible teams!")
        
        print(f"\n=== FINAL RESULTS AFTER AUTO-ASSIGNMENT ===")
        for team_name, team_data in teams.items():
            print(f"{team_name}: {len(team_data['players'])} players, ₹{team_data['budget']:.1f}Cr left")
    
    print(f"\n=== SUMMARY ===")
    distribution = [len(team['players']) for team in teams.values()]
    budgets = [f'₹{team["budget"]:.1f}Cr' for team in teams.values()]
    print(f"Distribution: {distribution}")
    print(f"Budgets left: {budgets}")