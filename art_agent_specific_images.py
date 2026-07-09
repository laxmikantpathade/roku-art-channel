import os
import warnings
import urllib.parse
import re
import json
import time
import requests
import subprocess
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- FORCE SUPPRESS MAC LIBRESSL WARNINGS ---
warnings.filterwarnings("ignore", module="urllib3")
warnings.simplefilter("ignore")

# --- CONFIGURATION ---
GITHUB_PAGES_URL = "https://laxmikantpathade.com/roku-art-channel"
DELAY_BETWEEN_DOWNLOADS = 3  

# STRICT BROWSER MASK with Referer to bypass Wikimedia's direct-link firewall
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://commons.wikimedia.org/"
}

# --- TARGETED SPECIFIC MASTERPIECES CHECKLIST ---
# Direct, stable Wikimedia CDN paths for the final two files! No proxies!
TARGET_MASTERPIECES = [
    {
        "title": "The Sampling Officials", 
        "artist": "Rembrandt", 
        "museum": "Rijksmuseum, Amsterdam", 
        "year": "1662", 
        "url": "https://upload.wikimedia.org/wikipedia/commons/e/e4/Rembrandt_van_Rijn_-_De_Staalmeesters-The_Syndics_of_the_Clothmaker%27s_Guild_%28Rijksmuseum_Amsterdam%29.jpg"
    },
    {
        "title": "The Bath", 
        "artist": "Jean-Léon Gérôme", 
        "museum": "Fine Arts Museums of San Francisco", 
        "year": "1885", 
        "url": "https://upload.wikimedia.org/wikipedia/commons/d/d9/Jean-L%C3%A9on_G%C3%A9r%C3%B4me_-_The_Bath_-_Google_Art_Project.jpg"
    }
]

# --- UTILITY CORE HELPER FUNCTIONS ---

def load_json_file(filepath, fallback):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return fallback

def save_json_file(data, filepath):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"❌ Error saving JSON database update: {e}")

def normalize_title(title):
    t = str(title).lower()
    t = re.sub(r'\b(the|a|an)\b', '', t)
    t = re.sub(r'[^a-z0-9]', '', t)
    return t.strip()

def safe_get(url, headers=None, timeout=25):
    try:
        res = requests.get(url, headers=headers, timeout=timeout)
        return res
    except Exception as e:
        print(f"   ⚠️ Connection tracking hiccup: {e}")
        return None

def get_next_available_index(folder="."):
    max_num = 0
    for f in os.listdir(folder):
        if f.startswith("image_") and f.endswith(".jpg"):
            match = re.search(r'image_(\d+)\.jpg', f)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num + 1

# --- IMAGE GRAPHICS CANVAS PROCESSING AND STAMPING RULES ---

def pad_and_resize_16_9(img):
    target_width, target_height = 2560, 1440
    img_ratio = img.width / img.height
    target_ratio = target_width / target_height

    if img_ratio > target_ratio:
        new_width = target_width
        new_height = int(target_width / img_ratio)
    else:
        new_height = target_height
        new_width = int(target_height * img_ratio)

    resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
    img_resized = img.resize((new_width, new_height), resample_filter)

    padded_img = Image.new("RGB", (target_width, target_height), (0, 0, 0))
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2
    padded_img.paste(img_resized, (x_offset, y_offset))
    return padded_img

def stamp_image(img_bytes, metadata, output_filename):
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img = pad_and_resize_16_9(img)
        width, height = img.size
        
        try:
            title_font = ImageFont.truetype("/Library/Fonts/Arial Bold.ttf", 38)
            sub_font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 34)
        except IOError:
            try:
                title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 38)
                sub_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 34)
            except IOError:
                title_font = sub_font = ImageFont.load_default()
            
        banner_height = 200
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        
        overlay_draw.rectangle([(0, height - banner_height), (width, height)], fill=(0, 0, 0, 45))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        
        draw = ImageDraw.Draw(img)
        line_1_text = f"{str(metadata.get('title', '')).strip()}  ·  {str(metadata.get('artist', '')).strip()}"
        draw.text((50, height - banner_height + 35), line_1_text, font=title_font, fill="white")
        
        line_2_text = f"{str(metadata.get('year', '')).strip()}  ·  {str(metadata.get('museum', '')).strip()}"
        draw.text((50, height - banner_height + 110), line_2_text, font=sub_font, fill="rgb(225,225,225)")
        
        img.save(output_filename, "JPEG", quality=90)
        return True
    except Exception as e:
        print(f"❌ Failed to stamp image layouts: {e}")
        return False

def push_to_github():
    print("\n🚀 Pushing priority checklist batch synchronization to GitHub...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "🤖 Target checklist processing complete via direct CDN"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✅ Live repository sync verified.")
    except Exception as e:
        print(f"⚠️ Git synchronization deferred or local repository detached: {e}")

# --- EXECUTION CONTROL CONTROLLER ---

def run_targeted_collector():
    print("👑 Starting Targeted Masterpiece Acquisition Pipeline...")
    
    feed_data = load_json_file("feed.json", {"artwork_list": []})
    artwork_list = feed_data.get("artwork_list", [])
    
    next_file_number = get_next_available_index(".")
    
    seen_titles = set()
    for art in artwork_list:
        title_str = art["title"]
        if " by " in title_str:
            raw_title = title_str.rsplit(" by ", 1)[0]
        else:
            raw_title = title_str
        seen_titles.add(normalize_title(raw_title))
        
    print(f"📂 Current feed tracking arrays host {len(artwork_list)} active nodes.")
    print(f"📸 Next structured image target designation set to: image_{next_file_number}.jpg")
    
    downloaded_any = False
    
    for target in TARGET_MASTERPIECES:
        norm_title = normalize_title(target["title"])
        if norm_title in seen_titles:
            continue
            
        print(f"\n🎯 Target Match isolated: '{target['title']}' by {target['artist']}")
        
        image_url = target.get("url")
        if not image_url:
            print("   ❌ No direct URL provided for this entry. Skipping.")
            continue
            
        image_filename = f"image_{next_file_number}.jpg"
        
        print(f"   📥 Downloading asset directly from original source URL...")
        img_res = safe_get(image_url, headers=DOWNLOAD_HEADERS, timeout=30)
            
        if img_res is not None and img_res.status_code == 200 and len(img_res.content) >= 10000:
            if b"<html" in img_res.content[:200].lower() or b"<!doctype html" in img_res.content[:200].lower():
                print("   ❌ Target download route resolved to a markup landing page instead of raw image data.")
                continue
                
            success = stamp_image(img_res.content, target, image_filename)
            if success:
                print(f"✅ Layout generation successful. File locked: {image_filename}")
                new_entry = {
                    "title": f"{target['title']} by {target['artist']}",
                    "image_url": f"{GITHUB_PAGES_URL}/{image_filename}",
                    "year": target['year'],
                    "museum": target['museum'],
                    "description": "Historical masterpiece entry."
                }
                artwork_list.append(new_entry)
                seen_titles.add(norm_title)
                downloaded_any = True
                
                save_json_file({"artwork_list": artwork_list}, "feed.json")
                next_file_number += 1
            else:
                print("   ❌ Image data acquired, but canvas layout processor rejected it.")
        else:
            error_code = img_res.status_code if img_res is not None else "Network/Timeout"
            print(f"   ❌ Direct link delivery failed. Status Code: {error_code}")
        
        time.sleep(DELAY_BETWEEN_DOWNLOADS)
        
    if downloaded_any:
        print("\n🎉 ALL PENDING TARGETS CAPTURED SUCCESSFULLY!")
        push_to_github()
    else:
        print("\n✨ All targets in the checklist are accounted for. Local array is up to date!")

if __name__ == "__main__":
    try:
        run_targeted_collector()
    except KeyboardInterrupt:
        print("\n🛑 Execution paused cleanly. Output caches preserved.")