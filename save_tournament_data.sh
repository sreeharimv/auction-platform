#!/bin/bash
# Helper script to save tournament data to git
# Run this after making changes to preserve data across deployments

echo "🔄 Saving tournament data to git..."
echo ""

# Add database and config
git add players.db config.json

# Check if there are changes
if git diff --staged --quiet; then
    echo "✅ No changes to save - data is already up to date"
else
    echo "📝 Changes detected:"
    git diff --staged --name-only
    echo ""
    
    # Prompt for commit message
    read -p "Enter commit message (or press Enter for default): " message
    
    if [ -z "$message" ]; then
        message="Update tournament data - $(date '+%Y-%m-%d %H:%M')"
    fi
    
    # Commit and push
    git commit -m "$message"
    
    echo ""
    read -p "Push to remote? (y/n): " push_confirm
    
    if [ "$push_confirm" = "y" ] || [ "$push_confirm" = "Y" ]; then
        git push
        echo ""
        echo "✅ Tournament data saved and pushed!"
        echo "🚀 Your next deployment will use this data"
    else
        echo ""
        echo "✅ Tournament data committed locally"
        echo "⚠️  Remember to run 'git push' to deploy changes"
    fi
fi

echo ""
echo "💡 Tip: Run this script after:"
echo "   - Adding/editing players"
echo "   - Changing tournament settings"
echo "   - Completing an auction"
