# Quick Start Guide

## 🚀 Your Tournament Data is Now in Git!

Your tournament data (players, config, auction results) is tracked in git and will persist across deployments.

## 📝 Workflow

### 1. Make Changes
- Add/edit players
- Update tournament settings
- Run your auction
- Assign captains

### 2. Save Your Data

**Easy Way (Recommended):**

Linux/Mac:
```bash
./save_tournament_data.sh
```

Windows:
```
save_tournament_data.bat
```

**Manual Way:**
```bash
git add players.db config.json
git commit -m "Update tournament data"
git push
```

### 3. Deploy
- If auto-deploy is enabled, your changes will deploy automatically
- Otherwise, manually trigger a deployment on your platform

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
