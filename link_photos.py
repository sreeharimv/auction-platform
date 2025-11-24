#!/usr/bin/env python3
"""
Script to link player photos to database records
"""
import sqlite3
import os
import re

DB_FILE = "players.db"
PHOTOS_DIR = "static/players"

def normalize_name(name):
    """Normalize name for matching (lowercase, remove spaces/special chars)"""
    return re.sub(r'[^a-z0-9]', '', name.lower())

def list_players_and_photos():
    """List all players and available photos"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT player_id, name, photo FROM players ORDER BY player_id")
    players = cursor.fetchall()
    conn.close()
    
    # Get available photos
    photos = []
    if os.path.exists(PHOTOS_DIR):
        photos = [f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
    
    print("\n=== Current Players ===")
    print(f"{'ID':<5} {'Name':<30} {'Current Photo':<30}")
    print("-" * 70)
    for player_id, name, photo in players:
        print(f"{player_id:<5} {name:<30} {photo or 'None':<30}")
    
    print(f"\n=== Available Photos ({len(photos)}) ===")
    for photo in sorted(photos):
        print(f"  - {photo}")
    print()

def auto_link_photos():
    """Automatically link photos based on name matching"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT player_id, name, photo FROM players ORDER BY player_id")
    players = cursor.fetchall()
    
    # Get available photos
    photos = []
    if os.path.exists(PHOTOS_DIR):
        photos = [f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
    
    # Create mapping of normalized names to photo files
    photo_map = {}
    for photo in photos:
        # Remove extension and normalize
        name_part = os.path.splitext(photo)[0]
        normalized = normalize_name(name_part)
        photo_map[normalized] = photo
    
    updates = []
    matched = 0
    unmatched = []
    
    for player_id, name, current_photo in players:
        normalized_name = normalize_name(name)
        
        # Try exact match first
        if normalized_name in photo_map:
            photo_file = photo_map[normalized_name]
            updates.append((photo_file, player_id))
            matched += 1
            print(f"✓ Matched: {name} → {photo_file}")
        else:
            # Try partial match
            found = False
            for photo_key, photo_file in photo_map.items():
                if photo_key in normalized_name or normalized_name in photo_key:
                    updates.append((photo_file, player_id))
                    matched += 1
                    print(f"~ Partial match: {name} → {photo_file}")
                    found = True
                    break
            
            if not found:
                unmatched.append((player_id, name))
    
    if updates:
        print(f"\n=== Updating {len(updates)} player photos ===")
        for photo, player_id in updates:
            cursor.execute("UPDATE players SET photo = ? WHERE player_id = ?", (photo, player_id))
        conn.commit()
        print(f"✓ Successfully updated {len(updates)} player photos!")
    
    if unmatched:
        print(f"\n=== {len(unmatched)} players without photo matches ===")
        for player_id, name in unmatched:
            print(f"  #{player_id}: {name}")
    
    conn.close()
    return matched, len(unmatched)

def manual_link_photo(player_id, photo_filename):
    """Manually link a photo to a player"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if player exists
    cursor.execute("SELECT name FROM players WHERE player_id = ?", (player_id,))
    result = cursor.fetchone()
    
    if not result:
        print(f"Error: Player with ID {player_id} not found!")
        conn.close()
        return False
    
    name = result[0]
    
    # Update the photo
    cursor.execute("UPDATE players SET photo = ? WHERE player_id = ?", (photo_filename, player_id))
    conn.commit()
    conn.close()
    
    print(f"✓ Linked {photo_filename} to player #{player_id} ({name})")
    return True

if __name__ == "__main__":
    print("\n" + "="*80)
    print("Player Photo Linking Tool")
    print("="*80)
    
    list_players_and_photos()
    
    print("\nOptions:")
    print("  1. Auto-link photos (match by name)")
    print("  2. Manual link (specify player ID and photo)")
    print("  3. View current status")
    print("  q. Quit")
    
    choice = input("\nEnter choice: ").strip()
    
    if choice == '1':
        print("\n=== Auto-linking photos ===")
        matched, unmatched = auto_link_photos()
        print(f"\nSummary: {matched} matched, {unmatched} unmatched")
        print("\nDone! Refresh the auction page to see the photos.")
    
    elif choice == '2':
        try:
            player_id = int(input("Enter Player ID: ").strip())
            photo = input("Enter photo filename (e.g., 'john.jpg'): ").strip()
            manual_link_photo(player_id, photo)
        except ValueError:
            print("Error: Invalid player ID")
    
    elif choice == '3':
        # Already displayed above
        pass
    
    elif choice.lower() == 'q':
        print("Exiting...")
    
    else:
        print("Invalid choice")
