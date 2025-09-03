# Palace Premier League Auction Platform

A comprehensive cricket auction management system built with Flask.

## Features

- **Player Management**: Add, edit, delete players with photos
- **Live Auction**: Real-time bidding interface
- **Sequential Auction**: Automated player-by-player auction
- **Team Management**: Track budgets, squads, and spending
- **Tournament Settings**: Configurable teams, budgets, and rules
- **Photo Upload**: Player photos with auto-resize
- **Export/Import**: CSV data management

## Deployment

### Local Development
```bash
pip install -r requirements.txt
python app.py
```

### Render Deployment
1. Connect GitHub repository
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `gunicorn app:app`

## Admin Access
- URL: `/admin`
- Password: `admin123`

## Configuration
- Tournament settings via `/tournament-settings`
- Player management via `/player-management`
- Live auction via `/auction`

## Tech Stack
- Flask (Python web framework)
- Pandas (Data management)
- Pillow (Image processing)
- Bootstrap CSS (UI styling)