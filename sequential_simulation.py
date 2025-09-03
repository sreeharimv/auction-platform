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
    "Palace Tuskers": {"budget": 25, "players": [], "captain": None},
    "Palace Titans": {"budget": 25, "players": [], "captain": None}, 
    "Palace Warriors": {"budget": 25, "players": [], "captain": None}
}

BASE_PRICE = 0.5  # 50L in Crores

def create_strategic_sequence():
    """Create auction sequence mixing high and low rated players throughout"""
    # Remove captains
    captains = ["Arjun", "Marsh", "Ram Manohar"]
    auction_players = {k: v for k, v in players.items() if k not in captains}
    
    # Categorize players
    premium = [(k, v) for k, v in auction_players.items() if v >= 90]  # 90+
    good = [(k, v) for k, v in auction_players.items() if 80 <= v < 90]  # 80-89
    average = [(k, v) for k, v in auction_players.items() if 65 <= v < 80]  # 65-79
    low = [(k, v) for k, v in auction_players.items() if v < 65]  # <65
    
    # Strategic sequence: Interleave categories so low players come between good ones
    sequence = []
    
    # Pattern: Premium -> Low -> Good -> Average -> Premium -> Low -> etc.
    all_lists = [premium, good, average, low]
    max_len = max(len(lst) for lst in all_lists)
    
    # Interleave players from different categories
    for i in range(max_len):
        # Add premium player if available
        if i < len(premium):
            sequence.append(premium[i])
        
        # Add low player early (when teams have budget)
        if i < len(low):
            sequence.append(low[i])
            
        # Add good player
        if i < len(good):
            sequence.append(good[i])
            
        # Add average player
        if i < len(average):
            sequence.append(average[i])
    
    return [name for name, rating in sequence]

def simulate_sequential_auction():
    print("=== SEQUENTIAL AUCTION SIMULATION ===\n")
    
    # Set captains
    captains = ["Arjun", "Marsh", "Ram Manohar"]
    team_names = list(teams.keys())
    
    for i, captain in enumerate(captains):
        teams[team_names[i]]["captain"] = captain
        teams[team_names[i]]["players"].append(captain)
        print(f"{team_names[i]} Captain: {captain} ({players[captain]} rating)")
    
    # Create strategic sequence
    auction_sequence = create_strategic_sequence()
    
    print(f"\n=== AUCTION SEQUENCE ===")
    for i, player in enumerate(auction_sequence, 1):
        print(f"{i:2d}. {player} (Rating: {players[player]})")
    
    print(f"\n=== AUCTION START ===")
    
    for round_num, player_name in enumerate(auction_sequence, 1):
        rating = players[player_name]
        print(f"\n--- Round {round_num}: {player_name} (Rating: {rating}) ---")
        
        # Check which teams can bid and need players
        eligible_teams = []
        for team_name, team_data in teams.items():
            current_players = len(team_data["players"])
            if current_players < 9:  # Max 9 players per team
                players_needed_after = max(0, 8 - current_players)  # Still need to reach 8 total
                max_bid = team_data["budget"] - (players_needed_after * BASE_PRICE)
                
                # Test our formula
                print(f"    {team_name}: {current_players} players, ₹{team_data['budget']:.1f}Cr left, need {players_needed_after} more → Max bid: ₹{max_bid:.1f}Cr")
                
                if max_bid >= BASE_PRICE:
                    eligible_teams.append((team_name, max_bid, current_players))
                else:
                    print(f"    {team_name}: Cannot bid (max_bid ₹{max_bid:.1f}Cr < base ₹{BASE_PRICE}Cr)")
        
        if not eligible_teams:
            print(f"❌ {player_name} - No teams can afford!")
            continue
        
        # Simulate bidding behavior based on player rating and team needs
        bids = []
        for team_name, max_bid, current_players in eligible_teams:
            # Check how many low-rated players this team already has
            team_low_players = sum(1 for p in teams[team_name]["players"] 
                                 if p in players and players[p] < 65)
            
            # Bidding probability based on rating and team situation
            base_probability = min(0.9, rating / 100 + 0.1)
            
            # Realistic team behavior: avoid accumulating too many weak players
            if rating < 65:  # Low-rated player
                if team_low_players >= 2:  # Already has 2+ weak players
                    base_probability *= 0.3  # Very reluctant to bid
                elif team_low_players >= 1:  # Already has 1 weak player
                    base_probability *= 0.6  # Somewhat reluctant
            
            # Teams more strategic about squad balance
            if rating < 70 and current_players >= 6:  # Late in auction, be selective
                base_probability *= 0.5
            
            # In sequential auction, teams MUST bid - but can be reluctant
            will_bid = random.random() < base_probability
            
            # Force bid if budget is very high (can't be too selective)
            if max_bid > 15 and rating >= 60:
                will_bid = True
            
            if will_bid:
                # Bid amount based on rating
                if rating >= 90:
                    bid_amount = min(random.uniform(3, 7), max_bid)
                elif rating >= 80:
                    bid_amount = min(random.uniform(1.5, 4), max_bid)
                elif rating >= 65:
                    bid_amount = min(random.uniform(0.5, 2), max_bid)
                else:
                    bid_amount = BASE_PRICE  # Only base price for low rated
                
                # Ensure bid respects our max bid formula
                if bid_amount >= BASE_PRICE and bid_amount <= max_bid:
                    bids.append((team_name, bid_amount))
                elif bid_amount > max_bid:
                    # Formula prevents overbidding
                    print(f"    {team_name}: Wanted to bid ₹{bid_amount:.1f}Cr but max allowed is ₹{max_bid:.1f}Cr")
                    bids.append((team_name, max_bid))  # Bid maximum allowed
        
        if bids:
            # Highest bidder wins
            winner, winning_bid = max(bids, key=lambda x: x[1])
            teams[winner]["players"].append(player_name)
            teams[winner]["budget"] -= winning_bid
            print(f"✅ SOLD to {winner} for ₹{winning_bid:.1f}Cr")
        else:
            # No bids - force assignment to team with highest budget (realistic auction)
            if eligible_teams:
                winner_team = max(eligible_teams, key=lambda x: x[1])[0]
                teams[winner_team]["players"].append(player_name)
                teams[winner_team]["budget"] -= BASE_PRICE
                print(f"✅ FORCED SALE to {winner_team} for ₹{BASE_PRICE}Cr (no bids - highest budget)")
            else:
                print(f"❌ {player_name} - NO ELIGIBLE TEAMS!")
    
    # Show final results
    print(f"\n=== FINAL RESULTS ===")
    total_assigned = 0
    for team_name, team_data in teams.items():
        print(f"\n{team_name}:")
        print(f"  Players: {len(team_data['players'])}")
        print(f"  Budget left: ₹{team_data['budget']:.1f}Cr")
        print(f"  Squad: {', '.join(team_data['players'])}")
        total_assigned += len(team_data["players"])
    
    # Check unsold players
    all_assigned = [player for team in teams.values() for player in team["players"]]
    unsold = [name for name in players.keys() if name not in all_assigned]
    
    print(f"\n❌ UNSOLD PLAYERS ({len(unsold)}):")
    for player in unsold:
        print(f"  {player} (Rating: {players[player]})")
    
    print(f"\nTotal assigned: {total_assigned}/26")
    if total_assigned == 26:
        print("✅ Perfect! All players assigned through sequential auction.")
    else:
        print(f"⚠️  {26 - total_assigned} players unassigned - this shouldn't happen in real auction!")
    
    if unsold:
        print(f"\n=== REMAINING PLAYERS (Should be 0 in sequential auction) ===")
        for player in unsold:
            print(f"  {player} - This shouldn't happen in real sequential auction!")
    
    print(f"\n=== FINAL DISTRIBUTION ===")
    distribution = [len(team['players']) for team in teams.values()]
    budgets = [f'₹{team["budget"]:.1f}Cr' for team in teams.values()]
    print(f"Team sizes: {distribution}")
    print(f"Budgets left: {budgets}")

if __name__ == "__main__":
    simulate_sequential_auction()