#!/usr/bin/env python3
"""
Simple script to update a player's name in the database
"""
import sqlite3
import sys

DB_FILE = "players.db"

def list_players():
    """List all players with their IDs"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT player_id, name, role, team, status FROM players ORDER BY player_id")
    players = cursor.fetchall()
    conn.close()
    
    print("\n=== Current Players ===")
    print(f"{'ID':<5} {'Name':<30} {'Role':<15} {'Team':<15} {'Status':<10}")
    print("-" * 80)
    for player in players:
        player_id, name, role, team, status = player
        print(f"{player_id:<5} {name:<30} {role or '-':<15} {team or '-':<15} {status or '-':<10}")
    print()

def update_player_name(player_id, new_name):
    """Update a player's name"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if player exists
    cursor.execute("SELECT name FROM players WHERE player_id = ?", (player_id,))
    result = cursor.fetchone()
    
    if not result:
        print(f"Error: Player with ID {player_id} not found!")
        conn.close()
        return False
    
    old_name = result[0]
    
    # Update the name
    cursor.execute("UPDATE players SET name = ? WHERE player_id = ?", (new_name, player_id))
    conn.commit()
    conn.close()
    
    print(f"\n✓ Successfully updated player #{player_id}")
    print(f"  Old name: {old_name}")
    print(f"  New name: {new_name}\n")
    return True

if __name__ == "__main__":
    print("\n" + "="*80)
    print("Player Name Update Tool")
    print("="*80)
    
    # List all players first
    list_players()
    
    # Get player ID
    try:
        player_id = input("Enter Player ID to update (or 'q' to quit): ").strip()
        if player_id.lower() == 'q':
            print("Exiting...")
            sys.exit(0)
        
        player_id = int(player_id)
        
        # Get new name
        new_name = input("Enter new name: ").strip()
        
        if not new_name:
            print("Error: Name cannot be empty!")
            sys.exit(1)
        
        # Confirm
        confirm = input(f"\nUpdate player #{player_id} to '{new_name}'? (yes/no): ").strip().lower()
        
        if confirm in ['yes', 'y']:
            update_player_name(player_id, new_name)
            print("Done! The change will be reflected when you refresh the auction page.")
        else:
            print("Update cancelled.")
    
    except ValueError:
        print("Error: Invalid player ID. Must be a number.")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(0)
