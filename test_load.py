#!/usr/bin/env python3
"""
Load test for Palace Premier League Auction Platform
Simulates multiple SSE connections and rapid bidding to test for lag issues
"""

import requests
import threading
import time
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

BASE_URL = "http://localhost:5000"

def get_admin_session():
    """Login and get admin session cookie"""
    session = requests.Session()
    # Login to admin
    login_data = {"password": "admin123"}
    response = session.post(f"{BASE_URL}/admin", data=login_data)
    if response.status_code == 200:
        return session
    else:
        print("Failed to login as admin")
        return None

def simulate_sse_connection(connection_id, duration=120):
    """Simulate SSE connection for specified duration"""
    print(f"SSE Connection {connection_id} starting...")
    try:
        response = requests.get(f"{BASE_URL}/events", stream=True, timeout=duration)
        message_count = 0
        for line in response.iter_lines():
            if line:
                message_count += 1
                if message_count % 10 == 0:
                    print(f"SSE {connection_id}: Received {message_count} messages")
    except Exception as e:
        print(f"SSE Connection {connection_id} error: {e}")
    finally:
        print(f"SSE Connection {connection_id} ended")

def make_bid(session, player_id, team, bid_num):
    """Simulate bid placement"""
    start_time = time.time()
    try:
        data = {"player_id": player_id, "team": team}
        response = session.post(f"{BASE_URL}/api/bid", json=data, timeout=10)
        end_time = time.time()
        duration = (end_time - start_time) * 1000  # Convert to milliseconds
        
        if response.status_code == 200:
            print(f"Bid {bid_num}: SUCCESS in {duration:.0f}ms")
        else:
            print(f"Bid {bid_num}: FAILED ({response.status_code}) in {duration:.0f}ms")
    except Exception as e:
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        print(f"Bid {bid_num}: ERROR in {duration:.0f}ms - {e}")

def make_sold(session, player_id, action_num):
    """Simulate marking player as sold"""
    start_time = time.time()
    try:
        data = {"player_id": player_id}
        response = session.post(f"{BASE_URL}/api/sold", json=data, timeout=10)
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        
        if response.status_code == 200:
            print(f"Sold {action_num}: SUCCESS in {duration:.0f}ms")
        else:
            print(f"Sold {action_num}: FAILED ({response.status_code}) in {duration:.0f}ms")
    except Exception as e:
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        print(f"Sold {action_num}: ERROR in {duration:.0f}ms - {e}")

def next_player(session, action_num):
    """Simulate next player action"""
    start_time = time.time()
    try:
        response = session.post(f"{BASE_URL}/next-player", timeout=10)
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        
        if response.status_code == 200:
            print(f"Next Player {action_num}: SUCCESS in {duration:.0f}ms")
        else:
            print(f"Next Player {action_num}: FAILED ({response.status_code}) in {duration:.0f}ms")
    except Exception as e:
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        print(f"Next Player {action_num}: ERROR in {duration:.0f}ms - {e}")

def load_test():
    """Main load test function"""
    print("Starting Palace Premier League Auction Load Test")
    print("=" * 50)
    
    # Get admin session
    admin_session = get_admin_session()
    if not admin_session:
        return
    
    print("Admin session established")
    
    # Test configuration
    NUM_SSE_CONNECTIONS = 15
    NUM_BIDS = 30
    NUM_SOLD_ACTIONS = 5
    NUM_NEXT_PLAYER = 3
    
    teams = ["Palace Tuskers", "Palace Titans", "Palace Warriors"]
    
    with ThreadPoolExecutor(max_workers=25) as executor:
        print(f"Starting {NUM_SSE_CONNECTIONS} SSE connections...")
        
        # Start SSE connections
        sse_futures = []
        for i in range(NUM_SSE_CONNECTIONS):
            future = executor.submit(simulate_sse_connection, i+1, 180)  # 3 minutes
            sse_futures.append(future)
        
        # Wait for connections to establish
        time.sleep(3)
        print("SSE connections established, starting auction actions...")
        
        # Rapid bidding test
        print(f"Testing {NUM_BIDS} rapid bids...")
        bid_futures = []
        for i in range(NUM_BIDS):
            team = teams[i % len(teams)]
            future = executor.submit(make_bid, admin_session, 1, team, i+1)
            bid_futures.append(future)
            time.sleep(0.2)  # 5 bids per second
        
        # Wait for bids to complete
        for future in bid_futures:
            future.result()
        
        time.sleep(2)
        
        # Test sold actions
        print(f"Testing {NUM_SOLD_ACTIONS} sold actions...")
        sold_futures = []
        for i in range(NUM_SOLD_ACTIONS):
            future = executor.submit(make_sold, admin_session, 1, i+1)
            sold_futures.append(future)
            time.sleep(1)
        
        # Wait for sold actions
        for future in sold_futures:
            future.result()
        
        time.sleep(2)
        
        # Test next player actions
        print(f"Testing {NUM_NEXT_PLAYER} next player actions...")
        next_futures = []
        for i in range(NUM_NEXT_PLAYER):
            future = executor.submit(next_player, admin_session, i+1)
            next_futures.append(future)
            time.sleep(2)
        
        # Wait for next player actions
        for future in next_futures:
            future.result()
        
        print("Load test completed! SSE connections will continue for 3 minutes...")
        print("Monitor your browser and server performance now.")
        
        # Wait for SSE connections to finish
        for future in sse_futures:
            future.result()

if __name__ == "__main__":
    print("Palace Premier League Auction - Load Test")
    print("Make sure your Flask app is running on http://localhost:5000")
    input("Press Enter to start load test...")
    
    start_time = datetime.now()
    load_test()
    end_time = datetime.now()
    
    print("=" * 50)
    print(f"Load test completed in {end_time - start_time}")
    print("Check server logs and browser performance for any issues.")