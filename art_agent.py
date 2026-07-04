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

# Massive, diverse list of Public Domain artists spanning historical importance
PUBLIC_DOMAIN_ARTISTS = [
    # --- The European Classics ---
    "Leonardo da Vinci", "Rembrandt", "Johannes Vermeer", "Claude Monet", 
    "Vincent van Gogh", "Diego Velázquez", "Caravaggio", "Titian", 
    "J.M.W. Turner", "Gustav Klimt", "Georges Seurat", "Francisco Goya",
    "Jean-Honoré Fragonard", "Sandro Botticelli", "Edgar Degas", "John William Waterhouse",
    "Pierre-Auguste Renoir", "Wassily Kandinsky", "Camille Pissarro", "Paul Cézanne",
    
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
    
    # --- Female Masters ---
    "Artemisia Gentileschi", "Élisabeth Vigée Le Brun", "Sofonisba Anguissola", 
    "Judith Leyster", "Rosa Bonheur", "Clara Peeters", "Rachel Ruysch", 
    "Hilma af Klint", "Berthe Morisot", "Angelica Kauffman",
    
    # --- Eastern European & Russian ---
    "Ilya Repin", "Ivan Aivazovsky", "Ivan Shishkin", "Mikhail Vrubel",
    "Józef Chełmoński", "Jan Matejko", "Tivadar Csontváry Kosztka"
]

session = requests.Session()

def safe_get(url, headers, params=None, timeout=15):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = session.get(url, headers=headers, params=params, timeout=timeout)
            if res.status_code == 429:
                wait_time = (attempt + 1) * 10  
                print(f"   ⏳ Rate limited (HTTP 429). Waiting {wait_time}s...")
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
    title = str(title).lower()
    title = re.sub(r'\b(the|a|an)\b', '', title)
    title = re.sub(r'[^a-z0-9]', '', title)
    return title

def get_curated_art_suggestion():
    """Asks Ollama to choose a masterpiece and grade its global artistic importance."""
    artist = random.choice(PUBLIC_DOMAIN_ARTISTS)
    
    prompt = (
        f"You are an expert art curator channeling catalog metrics from top replication indexing resources like TOPofART.\n"
        f"Select one real, highly-famed painting by the artist: {artist}.\n"
        "REQUIREMENTS:\n"
        "1. It MUST be created before 1920 (strictly public domain).\n"
        "2. Evaluate the artwork's global recognition, reproductive popularity, and historic impact on a scale from 0.0 to 10.0 (where 10.0 are elite masterworks like Mona Lisa, Starry Night, or The Kiss).\n"
        "3. Provide a high-quality, engaging 100-word history and description.\n"
        "You must respond ONLY with a raw JSON object matching this exact structure:\n"
        '{\n'
        '  "title": "Exact Artwork Title",\n'
        '  "artist": "Exact Artist Name",\n'
        '  "year": "Year Created",\n'
        '  "museum": "Current Location/Museum",\n'
        '  "importance_rating": 8.5,\n'
        '  "description": "A deep and beautiful background story about the painting\'s meaning and cultural legacy."\n'
        '}\n'
    )
    
    try:
        response = requests.post("http://localhost:11434/api/generate", 
                                 json={
                                     "model": "llama3.2", 
                                     "prompt": prompt, 
                                     "stream": False,
                                     "format": "json", 
                                     "options": {"temperature": 0.75}
                                 }, timeout=120) 
        
        if response.status_code == 200:
            raw_response = response.json().get("response", "").strip()
            return json.loads(raw_response)
    except Exception as e:
        print(f"⚠️ Error contacting Ollama: {e}")
    return None

def pad_and_resize_16_9(img):
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
        line_1_text = f"{str(metadata.get('title', '')).strip()}  ·  {str(metadata.get('artist', '')).strip()}"
        draw.text((50, height - banner_height + 25), line_1_text, font=title_font, fill="white")
        
        line_2_text = f"{str(metadata.get('year', '')).strip()}  ·  {str(metadata.get('museum', '')).strip()}"
        draw.text((50, height - banner_height + 80), line_2_text, font=sub_font, fill="rgb(225,225,225)")
        
        img.save(output_filename, "JPEG", quality=90)
        return True
    except Exception as e:
        print(f"❌ Failed to stamp image layouts: {e}")
        return False

def fetch_and_stamp_image(metadata, image_filename):
    """Searches text natively on Wikidata, then validates structure (P31) and decade era (P571) in code."""
    title_clean = str(metadata.get('title', '')).strip()
    artist_clean = str(metadata.get('artist', '')).strip()
    
    try:
        target_year = int(re.search(r'\d{4}', str(metadata.get('year', ''))).group())
    except (ValueError, TypeError, AttributeError):
        target_year = None

    # Artwork / Painting unique identification signatures
    PAINTING_SIGNATURES = ["Q3305213", "Q838948"]

    try:
        # Step 1: Query natively via clean text match terms (no syntax injection to prevent default fallback)
        search_query = f"{title_clean} {artist_clean}"
        search_params = {"action": "wbsearchentities", "search": search_query, "language": "en", "format": "json", "limit": 7}
        
        search_res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=search_params)
        if not search_res or search_res.status_code != 200:
            return False
        search_data = search_res.json()
        
        # Fallback 1: Try searching for just the painting name if artist pairing limits results
        if not search_data.get("search"):
            search_params["search"] = title_clean
            search_res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=search_params)
            if search_res and search_res.status_code == 200:
                search_data = search_res.json()

        if not search_data.get("search"):
            return False
        
        q_ids = [res["id"] for res in search_data["search"]]
        
        # Step 2: Grab the entity details to inspect P31 (type), P18 (image), and P571 (date)
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
        file_name = None
        
        # Step 3: Loop through candidates and validate their inner properties programmatically
        for q_id in q_ids:
            claims = entities.get(q_id, {}).get("claims", {})
            
            # Guard A: It MUST have an attached image
            if "P18" not in claims:
                continue
                
            # Guard B: Ensure it is an instance of a painting or visual art work (P31)
            if "P31" in claims:
                instance_ids = [c["mainsnak"]["datavalue"]["value"]["id"] for c in claims["P31"] if "datavalue" in c["mainsnak"]]
                if not any(idx in PAINTING_SIGNATURES for idx in instance_ids):
                    continue  # Drops books, biographies, etc.
            
            # Guard C: Historical Decade Validation Check (P571)
            if target_year and "P571" in claims:
                try:
                    time_datavalue = claims["P571"][0]["mainsnak"]["datavalue"]["value"]
                    wikidata_time_str = time_datavalue.get("time", "")
                    
                    year_match = re.search(r'\+?(-?\d{4})', wikidata_time_str)
                    if year_match:
                        wikidata_year = int(year_match.group(1))
                        # Skip if there's an anachronistic era drift of more than 15 years
                        if abs(wikidata_year - target_year) > 15:
                            print(f"   ⏳ Era Mismatch: Found matching text title, but Wikidata year ({wikidata_year}) drops out of target range ({target_year}). Skipping candidate...")
                            continue
                except Exception:
                    pass

            # Found a match that passes our programmatic check criteria!
            file_name = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
            break
                
        if not file_name:
            print("   ❌ Match Error: None of the visual text matches fit your structural or era criteria.")
            return False
        
        # Step 4: Ask Wikimedia Commons for the 1920px rendering layout pipeline URL
        commons_params = {"action": "query", "titles": f"File:{file_name}", "prop": "imageinfo", "iiprop": "url", "iiurlwidth": "1920", "format": "json"}
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
            img_res = safe_get(img_url, headers=DOWNLOAD_HEADERS, timeout=20)
            if img_res and img_res.status_code == 200:
                img_data = img_res.content
                if len(img_data) >= 15000:
                    return stamp_image(img_data, metadata, image_filename)
        
    except Exception as e:
        print(f"   ❌ Processing Error: {e}")
    return False

def push_to_github():
    print("\n🚀 Pushing progress milestone batch to GitHub...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Curated masterwork pipeline update"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print("✅ Successfully pushed to the cloud!")
    except Exception:
        print("⚠️ Automatic cloud push delayed.")

def run_bulk_collector():
    print("🤖 Smart Curated Bulk Collector initializing...")
    artwork_list = load_existing_progress()
    current_count = len(artwork_list)
    
    seen_titles = set()
    for art in artwork_list:
        raw_title = art["title"].split(" by ")[0] 
        seen_titles.add(normalize_title(raw_title))
    
    print(f"📂 Found {current_count} existing artworks in feed.json.")
    
    while current_count < TARGET_IMAGES:
        print(f"\n[{current_count + 1}/{TARGET_IMAGES}] 🧠 Asking Ollama for a curated masterpiece suggestion...")
        meta = get_curated_art_suggestion()
        
        if not meta or not meta.get("title") or not meta.get("artist"):
            time.sleep(1)
            continue
            
        raw_new_title = meta.get("title", "")
        normalized_new_title = normalize_title(raw_new_title)
        
        if normalized_new_title in seen_titles:
            print(f"⚠️ Already tracked '{raw_new_title}'. Skipping...")
            continue
            
        try:
            rating = float(meta.get("importance_rating", 0))
        except (ValueError, TypeError):
            rating = 0
            
        print(f"📋 Curation Review: '{raw_new_title}' by {meta.get('artist')} graded at a {rating}/10 importance.")
        
        if rating < 8.0:
            print(f"🛑 Dropped. Score is below the 8.0 quality threshold for the prime collection.")
            continue
            
        full_title_string = f"{raw_new_title} by {meta.get('artist')}"
        print(f"🌟 High-tier Masterpiece Accepted! Initiating fetch protocol...")
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
            seen_titles.add(normalized_new_title) 
            save_progress(artwork_list)
            current_count += 1
            
            if current_count % 25 == 0:
                push_to_github()
        else:
            print(f"⏭️ Media asset unretrievable on Wikidata. Skipping.")
        
        time.sleep(DELAY_BETWEEN_DOWNLOADS)
        
    print("\n🎉 BULK COLLECTION COMPLETE!")
    push_to_github()

if __name__ == "__main__":
    try:
        run_bulk_collector()
    except KeyboardInterrupt:
        print("\n🛑 Manual stop detected. Progress safely saved.")