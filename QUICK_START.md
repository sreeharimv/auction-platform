# Quick Start Guide

## 🚀 Your Tournament Data is Now in Git!

Your tournament data (players, config, auction results) is tracked in git and will persist across deployments.

## 📝 Two Workflows

### Workflow A: Changes Made Locally (Recommended)

If you edit files locally (database, config):

1. **Make changes locally**
2. **Save data:**
   ```bash
   ./save_tournament_data.sh    # Linux/Mac
   save_tournament_data.bat      # Windows
   ```
3. **Deploy**

### Workflow B: Changes Made via Web

If you make changes through the web interface:

1. **Make changes via web** (add players, run auction, etc.)
2. **Download database:**
   - Go to `/tournament-settings`
   - Click "📥 Download Database"
   - Save the file
3. **Replace local file:**
   - Replace your local `players.db` with the downloaded file
4. **Commit and push:**
   ```bash
   git add players.db config.json
   git commit -m "Update tournament data from web"
   git push
   ```
5. **Deploy**

## ⚠️ IMPORTANT

**If you make changes via web and deploy without downloading:**
- Your web changes will be LOST
- The deployment will use the old database from git
- Always download before deploying!

## 🎯 When to Save Data

Save your data after:
- ✅ Setting up your tournament (teams, settings)
- ✅ Adding all players
- ✅ Assigning captains
- ✅ Completing the auction
- ✅ Making any configuration changes

## 💡 Tips

1. **Before the auction**: Set up everything, save data, deploy
2. **During the auction**: No need to save (data is in memory)
3. **After the auction**: Save final results, deploy

## ⚠️ Important

- Your data is in git = it's backed up and version controlled
- Always commit after making changes you want to keep
- Don't forget to push after committing!

## 🔧 Troubleshooting

**Data reset after deployment?**
- Check if you committed and pushed your changes
- Verify players.db and config.json are in your git repo

**Can't run the script?**
- Linux/Mac: Make sure it's executable: `chmod +x save_tournament_data.sh`
- Windows: Right-click → Run as Administrator if needed

## 📚 More Info

- See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment guide
- See [README.md](README.md) for full documentation
