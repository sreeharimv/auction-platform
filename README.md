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
- **Secure Authentication**: Bcrypt password hashing with environment variables
- **Configuration Management**: Automatic backups and audit logging

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Variables Setup
The application uses environment variables for sensitive configuration:

```bash
# Copy the example environment file
cp .env.example .env
```

Edit `.env` and set your values:

```bash
# Generate a secure Flask secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Generate a password hash for your admin password
python -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
```

Update `.env` with your generated values:
```
FLASK_SECRET_KEY=your-generated-secret-key
ADMIN_PASSWORD_HASH=your-generated-password-hash
```

### 3. Run the Application

**Local Development:**
```bash
python app.py
```

**Production (Render/Heroku):**
```bash
gunicorn app:app
```

## Admin Access

- **URL**: `/admin`
- **Default Password**: `admin123` (⚠️ Change immediately in production!)
- **Change Password**: Go to `/tournament-settings` → Admin Password section

## Configuration Management

### Tournament Settings
Access via `/tournament-settings` to configure:
- Tournament name and currency symbol
- Team names and budgets
- Player limits (min/max per team)
- Base price and bid increments
- Admin password

### Configuration Backup & Restore
- **Automatic Backups**: Created before any configuration change
- **Retention**: Last 10 backups are kept
- **Export**: Download timestamped configuration files
- **Import**: Upload and validate configuration files
- **Audit Log**: Track all configuration changes

### Configuration Files
- `config.json` - Main configuration (tournament, teams, auction rules)
- `.env` - Environment variables (passwords, secret keys) - **Never commit!**
- `backups/` - Automatic configuration backups
- `audit.log` - Configuration change history

## Security Best Practices

1. **Change Default Password**: Immediately change the default admin password
2. **Secure Secret Key**: Use a strong, random Flask secret key
3. **Environment Variables**: Never commit `.env` file to version control
4. **HTTPS**: Use HTTPS in production
5. **Regular Backups**: Export configuration regularly
6. **Password Policy**: Use passwords with at least 8 characters

## Deployment

### Important: Data Persistence

✅ **This project stores tournament data in git** - your data is version controlled and backed up!

After making changes (adding players, running auction, updating settings):
```bash
./save_tournament_data.sh    # Linux/Mac
save_tournament_data.bat      # Windows
```

Or manually:
```bash
git add players.db config.json
git commit -m "Update tournament data"
git push
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for more details and alternative storage options.

### Quick Deployment Guide

#### Render.com
1. Connect GitHub repository
2. **Create a Persistent Disk** (1GB, mount at `/data`)
3. Add environment variables:
   ```
   FLASK_SECRET_KEY=<your-secret-key>
   ADMIN_PASSWORD_HASH=<your-password-hash>
   DATABASE_PATH=/data/players.db
   CONFIG_PATH=/data/config.json
   ```
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `gunicorn app:app`
6. After first deployment, copy initial files to persistent storage via Shell

#### Railway.app
1. Connect GitHub repository
2. **Add a Volume** (mount at `/data`)
3. Add environment variables (same as above)
4. Deploy and copy initial files to volume

### Environment Variables

Required:
```
FLASK_SECRET_KEY=<your-secret-key>
ADMIN_PASSWORD_HASH=<your-password-hash>
```

Optional (for persistent storage):
```
DATABASE_PATH=/data/players.db
CONFIG_PATH=/data/config.json
```

## Tech Stack
- **Flask** - Python web framework
- **Pandas** - Data management
- **Pillow** - Image processing
- **bcrypt** - Password hashing
- **python-dotenv** - Environment variable management
- **SQLite** - Database
- **Bootstrap CSS** - UI styling

## File Structure
```
.
├── app.py                      # Main application
├── config_manager.py           # Configuration management module
├── config.json                 # Tournament configuration
├── .env                        # Environment variables (not in git)
├── .env.example               # Environment template
├── players.db                  # SQLite database
├── backups/                    # Configuration backups
├── templates/                  # HTML templates
├── static/                     # CSS, images, assets
└── requirements.txt            # Python dependencies
```

## Troubleshooting

### "Invalid password" on login
- Check that `ADMIN_PASSWORD_HASH` in `.env` matches your password
- Regenerate the hash if needed

### "Configuration validation failed"
- Check `config.json` format matches the schema
- Ensure all required fields are present
- Verify numeric values are within acceptable ranges

### Sessions not persisting
- Ensure `FLASK_SECRET_KEY` is set in environment
- Check that the secret key doesn't change between restarts