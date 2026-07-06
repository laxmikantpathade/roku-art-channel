import json
import os
import re
from collections import defaultdict

FEED_FILE = "feed.json"

def normalize_text(text):
    """Cleans up text variations to ensure perfect structural matching."""
    return re.sub(r'[^a-z0-9]', '', str(text).lower())

def scan_for_duplicates():
    if not os.path.exists(FEED_FILE):
        print(f"❌ Error: {FEED_FILE} not found!")
        return

    with open(FEED_FILE, "r") as f:
        feed_data = json.load(f)
        
    artwork_list = feed_data.get("artwork_list", [])
    
    # Group entries by a combination of normalized title and artist
    catalog_groups = defaultdict(list)
    
    for art in artwork_list:
        full_title = art.get("title", "")
        if " by " in full_title:
            title = full_title.rsplit(" by ", 1)[0]
            artist = full_title.rsplit(" by ", 1)[1]
        else:
            title = full_title
            artist = "Unknown"
            
        unique_key = (normalize_text(title), normalize_text(artist))
        
        # Save key details for reporting
        catalog_groups[unique_key].append({
            "display_title": full_title,
            "filename": art.get("image_url", "").split("/")[-1],
            "year": art.get("year", "Unknown")
        })

    # --- REPORTING ---
    duplicate_groups = {k: v for k, v in catalog_groups.items() if len(v) > 1}
    
    if not duplicate_groups:
        print("✨ Excellence! Zero duplicates found in feed.json.")
        return

    print(f"🔍 Found {len(duplicate_groups)} unique artworks that have duplicate files:\n")
    print("=" * 80)
    
    total_duplicate_files = 0
    for idx, (key, entries) in enumerate(duplicate_groups.items(), 1):
        print(f"\n🎭 Duplicate Group #{idx}: '{entries[0]['display_title']}' ({entries[0]['year']})")
        print("-" * 50)
        for entry in entries:
            print(f"  📁 File: {entry['filename']}")
            total_duplicate_files += 1
            
    print("=" * 80)
    print(f"\n📊 Summary: {len(duplicate_groups)} artwork titles are split across {total_duplicate_files} files.")

if __name__ == "__main__":
    scan_for_duplicates()