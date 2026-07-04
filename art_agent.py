import os
import warnings
import urllib.parse
import re

# --- FORCE SUPPRESS MAC LIBRESSL WARNINGS ---
warnings.filterwarnings("ignore", module="urllib3")
warnings.simplefilter("ignore")

import json
import time
import requests
import random
import subprocess
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
TARGET_IMAGES = 2000
GITHUB_PAGES_URL = "https://laxmikantpathade.com/roku-art-channel"
DELAY_BETWEEN_DOWNLOADS = 5 

# Polite header for the JSON API
API_HEADERS = {
    "User-Agent": "RokuArtChannel/1.0 (https://laxmikantpathade.com; lpathade@example.com)"
}

# Chrome browser disguise to bypass the 403 CDN blocks on the image server
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://commons.wikimedia.org/"
}

# A massively expanded, globally diverse list of Public Domain artists
PUBLIC_DOMAIN_ARTISTS = [
    # --- The European Classics ---
    "Leonardo da Vinci", "Rembrandt", "Johannes Vermeer", "Claude Monet", 
    "Vincent van Gogh", "Diego Velázquez", "Caravaggio", "Titian", 
    "J.M.W. Turner", "Gustav Klimt", "Georges Seurat", "Francisco Goya",
    
    # --- East Asian Masters ---
    "Katsushika Hokusai", "Utagawa Hiroshige", "Katsushika Ōi", 
    "Hasegawa Tōhaku", "Kuroda Seiki", "Ito Jakuchu",
    "Shen Zhou", "Ma Yuan", "Qiu Ying", "Gao Fenghan", 
    "Jeong Seon", "Kim Hong-do", "Shin Yun-bok", 
    
    # --- South Asian & Islamic World ---
    "Raja Ravi Varma", "Nainsukh", "Bishandas", "Ustad Mansur", 
    "Kamāl ud-Dīn Behzād", "Reza Abbasi", "Mahmud al-Wasiti", 
    
    # --- The Americas & Pioneers ---
    "José María Velasco", "Joaquín Clausell", "Félix Émile Taunay", 
    "Robert S. Duncanson", "Edward Mitchell Bannister", 
    "Mary Cassatt", "Winslow Homer", "Thomas Cole", "John Singer Sargent",
    
    # --- Female Masters (Historically overlooked) ---
    "Artemisia Gentileschi", "Élisabeth Vigée Le Brun", "Sofonisba Anguissola", 
    "Judith Leyster", "Rosa Bonheur", "Clara Peeters", "Rachel Ruysch", 
    "Hilma af Klint", "Berthe Morisot", "Angelica Kauffman",
    
    # --- Eastern European & Russian ---
    "Ilya Repin", "Ivan Aivazovsky", "Ivan Shishkin", "Mikhail Vrubel",
    "Józef Chełmoński", "Jan Matejko", "Tivadar Csontváry Kosztka"
]

# Set up a global session to reuse connections and reduce server load
session = requests.Session()

def safe_get(url, headers, params=None, timeout=15):
    """A polite wrapper that automatically waits and retries if Wikimedia rate-limits us."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = session.get(url, headers=headers, params=params, timeout=timeout)
            if res.status_code == 429:
                wait_time = (attempt + 1) * 10  
                print(f"   ⏳ Rate limited (HTTP 429). Waiting {wait_time}s to let the server cool down...")
                time.sleep(wait_time)
                continue
            return res
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Connection hiccup: {e}. Retrying in 5s...")
            time.sleep(5)
    return None

def load_existing_progress():
    if os.path.exists("feed.json"):
        with open("feed.json", "r") as f:
            try:
                data = json.load(f)
                if "artwork_list" in data:
                    return data["artwork_list"]
            except json.JSONDecodeError:
                pass
    return []

def save_progress(artwork_list):
    with open("feed.json", "w") as f:
        json.dump({"artwork_list": artwork_list}, f, indent=4)

def normalize_title(title):
    """Strips punctuation, spaces, and articles to create a base string for duplicate checking."""
    title = title.lower()
    # Remove 'the', 'a', or 'an' if they appear as standalone words
    title = re.sub(r'\b(the|a|an)\b', '', title)
    # Remove all non-alphanumeric characters (spaces, hyphens, punctuation)
    title = re.sub(r'[^a-z0-9]', '', title)
    return title

def get_dynamic_art_suggestion():
    """Requests diverse ideas and 100-word descriptions from Ollama based on specific artists."""
    artist = random.choice(PUBLIC_DOMAIN_ARTISTS)
    
    prompt = (
        f"Provide one real, famous painting by the artist {artist}.\n"
        "It MUST have been created before the year 1920 to ensure it is in the public domain.\n"
        "Do not invent titles. Use the standard historical or widely known name.\n"
        "You must respond ONLY with a raw JSON object matching this exact format:\n"
        '{\n'
        '  "title": "Exact Artwork Title",\n'
        '  "artist": "Exact Artist Name",\n'
        '  "year": "Year Created",\n'
        '  "museum": "Current Location/Museum",\n'
        '  "description": "A captivating, 100-word background story about the painting\'s history, meaning, and cultural impact."\n'
        '}\n'
    )
    
    try:
        response = requests.post("http://localhost:11434/api/generate", 
                                 json={
                                     "model": "llama3.2", 
                                     "prompt": prompt, 
                                     "stream": False,
                                     "format": "json", 
                                     "options": {"temperature": 0.8}
                                 }, timeout=120) 
        
        if response.status_code != 200:
            print(f"⚠️ Ollama API returned status code {response.status_code}")
            return None
            
        raw_response = response.json().get("response", "").strip()
        return json.loads(raw_response)
        
    except json.JSONDecodeError as e:
        print(f"⚠️ Ollama generated invalid JSON: {e}")
    except requests.exceptions.Timeout:
        print("⚠️ Ollama took too long to write the description (Timeout).")
    except Exception as e:
        print(f"⚠️ Unexpected error contacting Ollama: {e}")
        
    return None

def pad_and_resize_16_9(img):
    """Preserves the entire painting by scaling it and padding with black bars for a 1920x1080 Roku canvas."""
    target_width, target_height = 1920, 1080
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
    """Pads to 16:9, then draws a softer left-aligned text layer with interpuncts (·)."""
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img = pad_and_resize_16_9(img)
        width, height = img.size 
        
        try:
            title_font = ImageFont.truetype("/Library/Fonts/Arial Bold.ttf", 29)
            sub_font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 26)
        except IOError:
            title_font = sub_font = ImageFont.load_default()
            
        banner_height = 150
        
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([(0, height - banner_height), (width, height)], fill=(0, 0, 0, 90))
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        
        draw = ImageDraw.Draw(img)
        
        line_1_text = f"{metadata.get('title', '').strip()}  ·  {metadata.get('artist', '').strip()}"
        draw.text((50, height - banner_height + 25), line_1_text, font=title_font, fill="white")
        
        line_2_text = f"{metadata.get('year', '').strip()}  ·  {metadata.get('museum', '').strip()}"
        draw.text((50, height - banner_height + 80), line_2_text, font=sub_font, fill="rgb(225,225,225)")
        
        img.save(output_filename, "JPEG", quality=90)
        return True
    except Exception as e:
        print(f"❌ Failed to stamp image layouts: {e}")
        return False

def fetch_and_stamp_image(metadata, image_filename):
    """Uses Wikidata search API to find the top 5 matches, then picks the first one with an image."""
    title_clean = metadata.get('title', '').strip()
    artist_clean = metadata.get('artist', '').strip()

    try:
        # Step 1: Search and grab the top 5 results
        search_query = f"{title_clean} {artist_clean}"
        search_params = {
            "action": "wbsearchentities",
            "search": search_query,
            "language": "en",
            "format": "json",
            "limit": 5
        }
        search_res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=search_params)
        
        if not search_res or search_res.status_code != 200:
            return False
            
        search_data = search_res.json()
        
        if not search_data.get("search"):
            search_params["search"] = title_clean
            search_res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=search_params)
            if not search_res or search_res.status_code != 200:
                return False
            search_data = search_res.json()
            if not search_data.get("search"):
                print("   ❌ Error: Could not find artwork on Wikidata.")
                return False
        
        # Extract the IDs for the top 5 matches
        q_ids = [res["id"] for res in search_data["search"][:5]]
        
        # Step 2: Query Wikidata for the data of ALL of those IDs in one single request
        entity_params = {
            "action": "wbgetentities",
            "ids": "|".join(q_ids),
            "props": "claims",
            "format": "json"
        }
        entity_res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=entity_params)
        if not entity_res or entity_res.status_code != 200:
            return False
            
        entities = entity_res.json().get("entities", {})
        
        # Step 3: Loop through our top 5 matches until we find one that has a picture (P18)
        file_name = None
        for q_id in q_ids:
            claims = entities.get(q_id, {}).get("claims", {})
            if "P18" in claims:
                file_name = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
                break
                
        if not file_name:
            print(f"   ❌ Error: None of the top {len(q_ids)} Wikidata results had an image attached. (Likely copyrighted)")
            return False
        
        # Step 4: Ask Wikimedia Commons for a web-friendly 1920px wide version
        commons_params = {
            "action": "query",
            "titles": f"File:{file_name}",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": "1920", 
            "format": "json"
        }
        commons_res = safe_get("https://commons.wikimedia.org/w/api.php", headers=API_HEADERS, params=commons_params)
        if not commons_res or commons_res.status_code != 200:
            return False
            
        img_url = None
        pages = commons_res.json().get("query", {}).get("pages", {})
        for page_id, page_info in pages.items():
            if "imageinfo" in page_info:
                info = page_info["imageinfo"][0]
                img_url = info.get("thumburl") or info.get("url")
                break
                
        if img_url:
            # Step 5: Actually download the image using the robust browser disguise
            img_res = safe_get(img_url, headers=DOWNLOAD_HEADERS, timeout=20)
            if img_res and img_res.status_code == 200:
                img_data = img_res.content
                if len(img_data) >= 15000:
                    return stamp_image(img_data, metadata, image_filename)
                else:
                    print(f"   ❌ Error: Image payload was suspiciously small ({len(img_data)} bytes).")
            else:
                status = img_res.status_code if img_res else 'Unknown'
                print(f"   ❌ Error: HTTP {status} when downloading image from {img_url}")
        else:
            print("   ❌ Error: Failed to retrieve direct image URL from Commons.")
                
    except Exception as e:
        print(f"   ❌ Network/Processing Error: {e}")
        
    return False

def push_to_github():
    print("\n🚀 Pushing progress milestone batch to GitHub...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Structured gallery milestone update"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✅ Successfully pushed to the cloud!")
    except Exception:
        print("⚠️ Automatic cloud push delayed.")

def run_bulk_collector():
    print("🤖 Bulk Art Collector initializing...")
    artwork_list = load_existing_progress()
    current_count = len(artwork_list)
    
    # 💥 THE NEW SMART DUPLICATE CHECKER 💥
    # Only stores the stripped-down, normalized core title
    seen_titles = set()
    for art in artwork_list:
        raw_title = art["title"].split(" by ")[0] # Grabs just the title part
        seen_titles.add(normalize_title(raw_title))
    
    print(f"📂 Found {current_count} existing artworks in feed.json.")
    
    while current_count < TARGET_IMAGES:
        print(f"\n[{current_count + 1}/{TARGET_IMAGES}] 🧠 Asking Ollama for a structured idea...")
        meta = get_dynamic_art_suggestion()
        
        if not meta or not meta.get("title") or not meta.get("artist"):
            time.sleep(1)
            continue
            
        raw_new_title = meta.get("title", "")
        normalized_new_title = normalize_title(raw_new_title)
        
        # Check against the aggressive normalized list instead of exact strings
        if normalized_new_title in seen_titles:
            print(f"⚠️ Already tracked a variation of '{raw_new_title}'. Skipping...")
            continue
            
        full_title_string = f"{raw_new_title} by {meta.get('artist')}"
        print(f"🎨 Ollama chose: {full_title_string}")
        image_filename = f"art_{current_count + 1}.jpg"
        
        success = fetch_and_stamp_image(meta, image_filename)
        
        if success:
            print(f"✅ Successfully stamped and saved as {image_filename}")
            new_entry = {
                "title": full_title_string,
                "image_url": f"{GITHUB_PAGES_URL}/{image_filename}",
                "year": meta.get("year"),
                "museum": meta.get("museum"),
                "description": meta.get("description", "")
            }
            artwork_list.append(new_entry)
            # Add the new, stripped-down title to memory
            seen_titles.add(normalized_new_title) 
            save_progress(artwork_list)
            current_count += 1
            
            if current_count % 25 == 0:
                push_to_github()
        else:
            print(f"⏭️ Media asset unretrievable. Skipping.")
        
        time.sleep(DELAY_BETWEEN_DOWNLOADS)
        
    print("\n🎉 BULK COLLECTION COMPLETE!")
    push_to_github()

if __name__ == "__main__":
    try:
        run_bulk_collector()
    except KeyboardInterrupt:
        print("\n🛑 Manual stop detected. Progress safely saved.")