import os
import re
import requests
import random
import textwrap
import json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import ollama

# 🔴 UPDATE THIS: Your future GitHub Pages URL
# Example: "https://laxmikantpathade.github.io/roku-art-channel"
GITHUB_PAGES_URL = "https://laxmikantpathade.com/roku-art-channel"

def ensure_master_list():
    file_name = "master_art_list.txt"
    if not os.path.exists(file_name):
        print("📝 Creating 'master_art_list.txt' with initial database...")
        initial_data = """Gentile da Fabriano · Adoration of the Magi · 1423 · Uffizi Gallery
Van Eyck · Arnolfini Portrait · 1434 · National Gallery
Leonardo da Vinci · The Last Supper · 1498 · Convent of Santa Maria delle Grazie
Botticelli · The Birth of Venus · 1486 · Uffizi Gallery
Hieronymus Bosch · The Garden of Earthly Delights · 1490 · Museo del Prado
Raphael · The School of Athens · 1511 · Apostolic Palace
Michelangelo · The Creation of Adam · 1512 · Sistine Chapel
Diego Velázquez · Las Meninas · 1656 · Museo del Prado
Vermeer · Girl with a Pearl Earring · 1665 · Mauritshuis
Vincent van Gogh · The Starry Night · 1889 · Museum of Modern Art
Georges Seurat · A Sunday Afternoon on the Island of La Grande Jatte · 1884 · Art Institute of Chicago
Edward Hopper · Nighthawks · 1942 · Art Institute of Chicago"""
        with open(file_name, "w") as f:
            f.write(initial_data)
    return file_name

def fetch_wikimedia_image(title, artist):
    search_query = f"{title} {artist}"
    url = "https://commons.wikimedia.org/w/api.php"
    
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": search_query, "gsrnamespace": 6, "gsrlimit": 1,
        "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 3840
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_info in pages.items():
            image_info = page_info.get("imageinfo", [])
            if image_info:
                return image_info[0].get("thumburl") or image_info[0].get("url")
    except Exception as e:
        print(f"      ↳ API Error: {e}")
    return None

def get_approved_masterpiece():
    list_file = ensure_master_list()
    
    with open(list_file, "r") as f:
        paintings = [line.strip() for line in f.readlines() if line.strip()]
        
    random.shuffle(paintings)
    attempts = 0
    max_attempts = 5
    
    for choice in paintings:
        if attempts >= max_attempts:
            break
            
        parts = [p.strip() for p in choice.split('·')]
        if len(parts) < 4:
            continue
            
        artist, title, year, museum = parts[0], parts[1], parts[2], parts[3]
        print(f"⚖️ AI Gatekeeper evaluating: '{title}' by {artist}...")
        
        try:
            response = ollama.chat(
                model='llama3.2', 
                messages=[
                    {'role': 'system', 'content': 'You are a generous art critic. A score of 10 is the Mona Lisa. A score of 8 is Nighthawks or American Gothic. Reply ONLY with a single number from 1 to 10.'},
                    {'role': 'user', 'content': f"Rate the cultural significance of the painting '{title}' by {artist}. Is it a widely recognized masterpiece?"}
                ]
            )
            reply = response['message']['content']
            score_match = re.search(r'\d+', reply)
            score = int(score_match.group()) if score_match else 0
            
            print(f"   ↳ AI Score: {score}/10")
            
            if score >= 7:
                print("   ✅ Approved! Fetching 4K image from Wikimedia...")
                image_url = fetch_wikimedia_image(title, artist)
                if image_url:
                    return {
                        "title": title, "artist": artist, "year": year, "museum": museum, "url": image_url
                    }
                else:
                    print("   ⚠️ Image not found on Wikimedia.")
            else:
                print("   ❌ Rejected (Score too low).")
                
        except Exception as e:
            print(f"   ↳ Error querying Gatekeeper: {e}")
            
        attempts += 1
        print("   Searching again...\n")

    print("⚠️ Max attempts reached. Engaging failsafe masterpiece...")
    return {
        "title": "The Starry Night", "artist": "Vincent van Gogh", "year": "1889", "museum": "Museum of Modern Art",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ea/Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg/3840px-Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg"
    }

def stamp_metadata_and_get_essay():
    art = get_approved_masterpiece()
    print(f"\n🎨 LOCKED IN: '{art['title']}' by {art['artist']} ({art['year']})")
    
    print("📥 Downloading high-resolution image...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(art['url'], headers=headers, timeout=20)
        response.raise_for_status() 
        
        with open("temp.jpg", "wb") as handler:
            handler.write(response.content)
            
        img = Image.open("temp.jpg").convert("RGB")
    except Exception as e:
        print(f"❌ Error downloading or opening image: {e}")
        return
        
    # 📺 16:9 TV Canvas Generation (4K UHD)
    TARGET_W, TARGET_H = 3840, 2160
    tv_canvas = Image.new("RGB", (TARGET_W, TARGET_H), (0, 0, 0))
    
    img_ratio = img.width / img.height
    target_ratio = TARGET_W / TARGET_H
    
    if img_ratio > target_ratio:
        new_w, new_h = TARGET_W, int(TARGET_W / img_ratio)
    else:
        new_h, new_w = TARGET_H, int(TARGET_H * img_ratio)
        
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    offset_x = (TARGET_W - new_w) // 2
    offset_y = (TARGET_H - new_h) // 2
    tv_canvas.paste(img_resized, (offset_x, offset_y))
    
    draw = ImageDraw.Draw(tv_canvas)
    
    raw_line1 = f"{art['artist']} · {art['title']}"
    wrapped_line1 = textwrap.fill(raw_line1, width=70)
    line2 = f"{art['museum']} · {art['year']}"
    stamp_text = f"{wrapped_line1}\n{line2}"
    
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 72)
    except IOError:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 72)
        except IOError:
            font = ImageFont.load_default()
    
    x_position = 180
    y_position = TARGET_H - 280
    
    draw.text((x_position + 4, y_position + 4), stamp_text, fill=(0, 0, 0), font=font) 
    draw.text((x_position, y_position), stamp_text, fill=(200, 200, 200), font=font) 
    
    tv_canvas.save("stamped_masterpiece.jpg", "JPEG", quality=100)
    print("💾 Success! 4K UHD Image saved as 'stamped_masterpiece.jpg'.")
    
    print("🖥️ Prompting Local Ollama Engine for historical background...")
    essay_text = "No essay generated."
    try:
        response = ollama.chat(
            model='llama3.2', 
            messages=[
                {'role': 'system', 'content': 'You are an elite museum art curator. Provide insightful historical context.'},
                {'role': 'user', 'content': f"Write a compelling 50-to-100-word background narrative essay about the painting '{art['title']}' by {art['artist']} ({art['year']}). Focus on why it is historically significant. Keep it strictly under 100 words total, plain text only."}
            ]
        )
        essay_text = response['message']['content'].strip()
        print(f"\n📜 Local AI Curator Essay:\n{essay_text}\n")
    except Exception as e:
        print(f"❌ Ollama Local Processing Error: {e}")

    # 🔴 NEW: Generate the Roku JSON Feed
    print("📄 Generating Roku 'feed.json'...")
    feed_data = {
        "channelName": "AI Masterpiece Curator",
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "currentArtwork": {
            "title": art['title'],
            "artist": art['artist'],
            "year": art['year'],
            "museum": art['museum'],
            "image_url": f"{GITHUB_PAGES_URL}/stamped_masterpiece.jpg",
            "essay": essay_text
        }
    }
    
    with open("feed.json", "w") as json_file:
        json.dump(feed_data, json_file, indent=4)
    print("✅ feed.json successfully created! Ready for GitHub.")

if __name__ == "__main__":
    stamp_metadata_and_get_essay()