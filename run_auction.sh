#!/bin/bash
# run_auction.sh
# Script to activate venv and run the auction app

PROJECT_DIR=/home/sreeh007/wslprojects/ppl_auction_platform
cd $PROJECT_DIR || exit

# Create venv if it does not exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    python3 -m pip install --upgrade pip
    python3 -m pip install -r requirements.txt
else
    source .venv/bin/activate
    python3 -m pip install -r requirements.txt
fi

echo "Starting Local Auction Platform..."
python3 app.py
