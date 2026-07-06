import os
import json
import re
import shutil

FEED_FILE = "feed.json"
NEW_FEED_FILE = "feed.json" 

def normalize_string(text):
    return str(text).lower().strip()

def extract_year(year_val):
    """Parses numeric year strings cleanly for accurate sorting alignment."""
    try:
        match = re.search(r'\d+', str(year_val))
        return int(match.group(0)) if match else 0
    except Exception:
        return 0

def process_catalog():
    if not os.path.exists(FEED_FILE):
        print(f"❌ Error: {FEED_FILE} not found!")
        return

    with open(FEED_FILE, "r") as f:
        feed_data = json.load(f)
    
    original_list = feed_data.get("artwork_list", [])
    total_entries = len(original_list)
    print(f"📂 Loaded {total_entries} artwork entries from metadata catalog.")

    # --- PHASE 1: PREPARE SORT KEYS ---
    for art in original_list:
        title_str = art.get("title", "")
        if " by " in title_str:
            artist_name = title_str.rsplit(" by ", 1)[1]
        else:
            artist_name = "Unknown"

        art["_sort_artist"] = normalize_string(artist_name)
        art["_sort_year"] = extract_year(art.get("year", 0))

    # --- PHASE 2: SORT BY ARTIST THEN YEAR ---
    # Keeps all matching records together so you can spot duplicates next to each other
    sorted_artworks = sorted(original_list, key=lambda x: (x["_sort_artist"], x["_sort_year"]))

    # --- PHASE 3: CONVERT FILENAMES TO image_X.jpg ---
    clean_artwork_list = []
    new_index = 1

    print("🚚 Creating sequential 'image_X.jpg' copies based on sorted layout...")
    for art in sorted_artworks:
        old_url = art.get("image_url", "")
        old_filename = old_url.split("/")[-1]
        
        if not os.path.exists(old_filename):
            print(f"   ⚠️ Local file missing on disk: {old_filename}. Record omitted.")
            continue

        new_filename = f"image_{new_index}.jpg"
        
        # Safely copy old file content to the new image_X naming format
        shutil.copy2(old_filename, new_filename)

        # Update the remote configuration values
        base_url = old_url.rsplit("/", 1)[0]
        art["image_url"] = f"{base_url}/{new_filename}"
        
        # Strip tracking properties before writing to disk
        del art["_sort_artist"]
        del art["_sort_year"]

        clean_artwork_list.append(art)
        new_index += 1

    # Overwrite feed configuration with clean sorted state
    with open(NEW_FEED_FILE, "w") as f:
        json.dump({"artwork_list": clean_artwork_list}, f, indent=4)

    print(f"\n🎉 DONE! Catalog sorted and mapped to image_X schema.")
    print(f"📝 {len(clean_artwork_list)} records updated inside local {NEW_FEED_FILE}.")

if __name__ == "__main__":
    process_catalog()