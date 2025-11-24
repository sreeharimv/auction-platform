# CSV Import Guide with Photos

## How to Import Players with Photos

### Step 1: Prepare Your Photos

Place all player photos in the `static/players/` folder with any filename you want:

```
static/players/
├── sreekanth.jpg
├── appu.jpg
├── marsh.jpg
├── govind.jpg
└── raman.jpg
```

**Photo Requirements:**
- Any image format (JPG, PNG, GIF, etc.)
- Any size (will be auto-resized to 200x200px)
- Square photos work best

### Step 2: Create Your CSV

Create a CSV file with a `photo` column containing the filenames:

```csv
name,role,base_price,age,batting_style,bowling_style,photo
Sreekanth,Batsman,5000000,44,Left-hand Bat,Right-arm Medium,sreekanth.jpg
Appu,All-Rounder,5000000,,Right-hand Bat,Right-arm Fast,appu.jpg
Marsh,Batsman,5000000,,Right-hand Bat,,marsh.jpg
```

**CSV Columns:**
- **Required:** name, role, base_price
- **Optional:** age, batting_style, bowling_style, photo
- **Photo column:** Just the filename (not the full path)

### Step 3: Import via Web Interface

1. Go to `/player-management`
2. Click "Choose File" under "Upload Players from CSV"
3. Select your CSV file
4. Click "Upload"

### What Happens:

✅ **If photo file exists:** Photo is linked to the player
✅ **If photo file missing:** Player is imported without photo (warning shown)
✅ **If photo column empty:** Player is imported without photo
✅ **If photo column missing:** All players imported without photos

### Example CSV Templates:

**With Photos:**
See `players_template_with_photos.csv`

**Without Photos:**
```csv
name,role,base_price
Sreekanth,Batsman,5000000
Appu,All-Rounder,5000000
```

### Tips:

1. **Filename matching:** Make sure photo filenames in CSV exactly match files in `static/players/`
2. **Case sensitive:** `sreekanth.jpg` ≠ `Sreekanth.jpg` on some systems
3. **Extensions:** Include the file extension (.jpg, .png, etc.)
4. **Spaces:** Avoid spaces in filenames (use `sreekanth.jpg` not `sreekanth photo.jpg`)

### Troubleshooting:

**"Photo not found" warning:**
- Check that the file exists in `static/players/` folder
- Check filename spelling and case
- Check file extension matches

**Photos not showing:**
- Clear browser cache
- Check that files are actually in `static/players/` folder
- Verify filenames match exactly

### After Import:

The system will:
1. Import all player data
2. Link photos that exist in `static/players/`
3. Show warnings for any missing photos
4. Players without photos will show the default placeholder

You can always upload photos later using the "Upload" button next to each player in the player management page.
