# Deployment Guide

## Problem: Data Resets on Deployment

If your tournament data (players, teams, configuration) resets to defaults after each deployment, it's because the database and config files are being overwritten from git.

## ✅ Current Solution: Git-Based Data Storage (Free)

This project is configured to store tournament data in git. This means:
- ✅ **Free** - No paid storage needed
- ✅ **Simple** - No complex setup
- ✅ **Backed up** - Your data is version controlled
- ⚠️ **Manual** - You need to commit after changes

### How It Works

1. Your `players.db` and `config.json` are tracked in git
2. When you deploy, the latest committed version is used
3. After making changes, commit and push to preserve data

### Quick Start

After making changes to your tournament (players, settings, auction results):

**Linux/Mac:**
```bash
./save_tournament_data.sh
```

**Windows:**
```
save_tournament_data.bat
```

**Or manually:**
```bash
git add players.db config.json
git commit -m "Update tournament data"
git push
```

Then redeploy (or wait for auto-deploy if enabled).

---

## Alternative: Use Persistent Storage (Paid)

### For Render.com

1. **Create a Persistent Disk**:
   - Go to your service dashboard
   - Click "Disks" in the left sidebar
   - Click "New Disk"
   - Name: `auction-data`
   - Size: 1GB (minimum)
   - Mount Path: `/data`

2. **Update Environment Variables**:
   Add these to your Render environment variables:
   ```
   DATABASE_PATH=/data/players.db
   CONFIG_PATH=/data/config.json
   ```

3. **Initial Setup** (one-time):
   - SSH into your Render instance or use the Shell
   - Copy initial files to persistent storage:
   ```bash
   cp players.db /data/players.db
   cp config.json /data/config.json
   ```

### For Railway.app

1. **Add a Volume**:
   - Go to your service settings
   - Click "Volumes"
   - Add new volume
   - Mount path: `/data`

2. **Set Environment Variables**:
   ```
   DATABASE_PATH=/data/players.db
   CONFIG_PATH=/data/config.json
   ```

3. **Initial Setup**:
   - Use Railway CLI or dashboard shell
   - Copy files to volume:
   ```bash
   cp players.db /data/players.db
   cp config.json /data/config.json
   ```

### For Heroku

1. **Use Heroku Postgres** (for database):
   - Add Heroku Postgres addon
   - Update app to use PostgreSQL instead of SQLite

2. **Use S3 or similar** (for config):
   - Store config.json in AWS S3, Google Cloud Storage, or similar
   - Update app to read from cloud storage

## Alternative: Keep Files in Git (Not Recommended)

If you can't use persistent storage, you can keep the files in git, but you'll need to:

1. **Remove from .gitignore**:
   - Remove `players.db` and `config.json` from `.gitignore`

2. **Commit your data**:
   ```bash
   git add players.db config.json
   git commit -m "Update tournament data"
   git push
   ```

3. **Repeat after every change**:
   - Every time you update players or config, commit and push
   - This is tedious and not recommended for production

## Recommended Approach

**Use persistent storage** - it's the proper way to handle user data in production deployments. Your data will persist across deployments and won't be lost.

## Backup Strategy

Regardless of which method you use:

1. **Regular Backups**:
   - Use the "Export Config" feature in tournament settings
   - Export player data regularly via the player management page

2. **Automated Backups**:
   - Set up a cron job or scheduled task to backup your database
   - Store backups in cloud storage (S3, Google Cloud Storage, etc.)

3. **Version Control for Config**:
   - Keep `config.json.example` in git as a template
   - Never commit actual `config.json` with real data

## Testing Persistent Storage

After setting up persistent storage:

1. Make a change (add a player, update config)
2. Trigger a deployment
3. Verify your changes are still there after deployment

If data persists, you're all set! If not, check that:
- The volume is properly mounted
- Environment variables are set correctly
- The app is reading from the correct paths
