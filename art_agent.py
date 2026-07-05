import os
import warnings
import urllib.parse
import re
import json
import time
import requests
import random
import subprocess
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- FORCE SUPPRESS MAC LIBRESSL WARNINGS ---
warnings.filterwarnings("ignore", module="urllib3")
warnings.simplefilter("ignore")

# --- CONFIGURATION ---
TARGET_IMAGES = 2000
GITHUB_PAGES_URL = "https://laxmikantpathade.com/roku-art-channel"
DELAY_BETWEEN_DOWNLOADS = 10 
SPARQL_CACHE_FILE = "sparql_cache.json"

# Polite headers for the data search (Wikidata loves Bots)
API_HEADERS = {
    "User-Agent": "RokuArtChannel/2.0 (https://laxmikantpathade.com; lpathade@example.com) Python-requests/2.31"
}

# Browser mask for the heavy image CDN (Wikimedia Commons hates Bots)
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "image/jpeg,image/png,image/webp,*/*;q=0.8"
}

PUBLIC_DOMAIN_ARTISTS = [
    "Leonardo da Vinci", "Rembrandt", "Johannes Vermeer", "Claude Monet", 
    "Vincent van Gogh", "Diego Velázquez", "Caravaggio", "Titian", 
    "J.M.W. Turner", "Gustav Klimt", "Georges Seurat", "Francisco Goya",
    "Jean-Honoré Fragonard", "Sandro Botticelli", "Edgar Degas", "John William Waterhouse",
    "Pierre-Auguste Renoir", "Wassily Kandinsky", "Camille Pissarro", "Paul Cézanne",
    "Katsushika Hokusai", "Utagawa Hiroshige", "Katsushika Ōi", "Hasegawa Tōhaku", 
    "Kuroda Seiki", "Ito Jakuchu", "Shen Zhou", "Ma Yuan", "Qiu Ying", "Gao Fenghan", 
    "Jeong Seon", "Kim Hong-do", "Shin Yun-bok", "Raja Ravi Varma", "Nainsukh", 
    "Bishandas", "Ustad Mansur", "Kamāl ud-Dīn Behzād", "Reza Abbasi", "Mahmud al-Wasiti", 
    "José María Velasco", "Joaquín Clausell", "Félix Émile Taunay", "Robert S. Duncanson", 
    "Edward Mitchell Bannister", "Mary Cassatt", "Winslow Homer", "Thomas Cole", 
    "John Singer Sargent", "Artemisia Gentileschi", "Élisabeth Vigée Le Brun", 
    "Sofonisba Anguissola", "Judith Leyster", "Rosa Bonheur", "Clara Peeters", 
    "Rachel Ruysch", "Hilma af Klint", "Berthe Morisot", "Angelica Kauffman",
    "Ilya Repin", "Ivan Aivazovsky", "Ivan Shishkin", "Mikhail Vrubel",
    "Józef Chełmoński", "Jan Matejko", "Tivadar Csontváry Kosztka"
]

session = requests.Session()

def load_json_file(filename, default_val):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return default_val

def save_json_file(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def safe_get(url, headers, params=None, timeout=20):
    for attempt in range(4):
        try:
            res = session.get(url, headers=headers, params=params, timeout=timeout, allow_redirects=True)
            if res.status_code == 429:
                retry_after = res.headers.get("Retry-After")
                wait_time = int(retry_after) if retry_after else (attempt + 1) * 30
                print(f"   ⏳ Rate Limit hit (HTTP 429). Pausing strictly for {wait_time}s...")
                time.sleep(wait_time)
                continue
            return res
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Connection hiccup: {e}. Retrying in 5s...")
            time.sleep(5)
    return None

def normalize_title(title):
    title = str(title).lower()
    title = re.sub(r'\b(the|a|an)\b', '', title)
    title = re.sub(r'[^a-z0-9]', '', title)
    return title

def get_next_available_index(folder="."):
    """Scans the folder to locate the highest existing art_X.jpg and returns X + 1."""
    max_num = 0
    for f in os.listdir(folder):
        if f.startswith("art_") and f.endswith(".jpg"):
            match = re.search(r'art_(\d+)\.jpg', f)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num + 1

def get_real_painting_from_wikidata(artist_name, seen_titles, sparql_cache):
    """Pulls from local hard-drive cache first. Uses SPARQL only if cache is empty."""
    
    # 1. Check our persistent cache first
    if artist_name in sparql_cache:
        if sparql_cache[artist_name]: # We have paintings!
            idx = random.randint(0, len(sparql_cache[artist_name]) - 1)
            painting = sparql_cache[artist_name].pop(idx)
            save_json_file(sparql_cache, SPARQL_CACHE_FILE) # Update the file
            return painting
        else:
            return None

    print(f"   🌐 Cache miss for {artist_name}. Executing SPARQL query to Wikidata...")
    time.sleep(5) # Polite delay before SPARQL

    # 2. Look up the artist's QID
    search_params = {"action": "wbsearchentities", "search": artist_name, "language": "en", "format": "json", "limit": 1}
    res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=search_params)
    if not res or not res.json().get('search'): 
        sparql_cache[artist_name] = [] 
        save_json_file(sparql_cache, SPARQL_CACHE_FILE)
        return None
        
    artist_qid = res.json()['search'][0]['id']

    # 3. Pull 100 paintings at once via SPARQL
    query = f"""
    SELECT ?artworkLabel ?year ?museumLabel ?image WHERE {{
      ?artwork wdt:P31 wd:Q3305213;
               wdt:P170 wd:{artist_qid};
               wdt:P18 ?image;
               wdt:P571 ?date.
      BIND(YEAR(?date) AS ?year)
      OPTIONAL {{ ?artwork wdt:P195 ?museum. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 100
    """
    
    headers = {"Accept": "application/sparql-results+json", **API_HEADERS}
    res = safe_get("https://query.wikidata.org/sparql", headers=headers, params={'query': query})
    
    if not res: 
        return None
    
    results = res.json().get('results', {}).get('bindings', [])
    valid_paintings = []
    
    # 4. Clean up the data
    for r in results:
        title = r.get('artworkLabel', {}).get('value', '')
        if not title or re.match(r'^Q\d+', title): 
            continue
            
        norm_title = normalize_title(title)
        if norm_title in seen_titles:
            continue

        museum = r.get('museumLabel', {}).get('value', 'Historical Collection')
        if re.match(r'^Q\d+', museum):
            museum = "Historical Collection"
            
        valid_paintings.append({
            'title': title,
            'artist': artist_name,
            'year': r.get('year', {}).get('value', 'Unknown'),
            'museum': museum,
            'image_url': r.get('image', {}).get('value', '')
        })
        
    # 5. Store them permanently on the hard drive and return one
    sparql_cache[artist_name] = valid_paintings
    save_json_file(sparql_cache, SPARQL_CACHE_FILE)
    
    if valid_paintings:
        idx = random.randint(0, len(sparql_cache[artist_name]) - 1)
        painting = sparql_cache[artist_name].pop(idx)
        save_json_file(sparql_cache, SPARQL_CACHE_FILE)
        return painting
        
    return None

def review_painting_with_ollama(painting_meta):
    prompt = (
        f"You are an expert art curator.\n"
        f"Review this REAL artwork for inclusion in our premium catalog:\n"
        f"Title: {painting_meta['title']}\n"
        f"Artist: {painting_meta['artist']}\n"
        f"Year: {painting_meta['year']}\n\n"
        "REQUIREMENTS:\n"
        "1. Evaluate its global historical importance on a scale from 0.0 to 10.0.\n"
        "2. Provide a high-quality, engaging 100-word history and description.\n"
        "Respond ONLY with a raw JSON object matching this exact structure:\n"
        '{\n'
        '  "importance_rating": 8.5,\n'
        '  "description": "..."\n'
        '}\n'
    )
    
    try:
        response = requests.post("http://localhost:11434/api/generate", 
                                 json={"model": "llama3.2", "prompt": prompt, "stream": False, "format": "json"}, 
                                 timeout=60)
        if response.status_code == 200:
            return json.loads(response.json().get("response", "").strip())
    except Exception as e:
        print(f"⚠️ Ollama Error: {e}")
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
    
    # Load primary feed and build seen titles
    feed_data = load_json_file("feed.json", {"artwork_list": []})
    artwork_list = feed_data.get("artwork_list", [])
    
    # 🌟 NEW DYNAMIC SLOT CALCULATION 🌟
    # Calculate file numbering based on the actual physical files left on your disk
    next_file_number = get_next_available_index(".")
    
    # Keep historical logs synced with total count to keep the loop conditional clear
    current_count = len(artwork_list)
    
    seen_titles = set()
    for art in artwork_list:
        raw_title = art["title"].split(" by ")[0] 
        seen_titles.add(normalize_title(raw_title))
        
    # Load persistent SPARQL Cache
    sparql_cache = load_json_file(SPARQL_CACHE_FILE, {})
    
    print(f"📂 Found {current_count} historical metadata rows in feed.json.")
    print(f"🚀 Next safe file naming sequence begins at: art_{next_file_number}.jpg")
    print(f"🗃️ Loaded SPARQL Cache containing data for {len(sparql_cache.keys())} artists.")
    
    while current_count < TARGET_IMAGES:
        artist = random.choice(PUBLIC_DOMAIN_ARTISTS)
        print(f"\n[{current_count + 1}/{TARGET_IMAGES}] 🔍 Processing {artist}...")
        
        painting_meta = get_real_painting_from_wikidata(artist, seen_titles, sparql_cache)
        
        if not painting_meta:
            print("   ⏭️ No historical assets found for this artist. Skipping...")
            if artist in PUBLIC_DOMAIN_ARTISTS:
                PUBLIC_DOMAIN_ARTISTS.remove(artist)
            time.sleep(1)
            continue
            
        print(f"   🖼️ Found verified piece: '{painting_meta['title']}' ({painting_meta['year']})")
        print(f"   🧠 Asking Ollama to review and write a catalog description...")
        
        ollama_review = review_painting_with_ollama(painting_meta)
        if not ollama_review:
            continue
            
        try:
            rating = float(ollama_review.get("importance_rating", 0))
        except (ValueError, TypeError):
            rating = 0
            
        print(f"📋 Curation Review Graded at: {rating}/10 importance.")
        
        if rating < 8.0:
            print(f"🛑 Dropped. Score is below the 8.0 quality threshold.")
            seen_titles.add(normalize_title(painting_meta['title']))
            continue
            
        print(f"🌟 High-tier Masterpiece Accepted! Downloading asset...")
        
        # 🌟 USE DYNAMIC IDENTIFIER FOR STORAGE 🌟
        image_filename = f"art_{next_file_number}.jpg"
        base_image_url = painting_meta['image_url']
        download_url = f"{base_image_url}?width=1920"
        
        # 1. Try fetching the 1920px thumbnail
        img_res = safe_get(download_url, headers=DOWNLOAD_HEADERS, timeout=20)
        
        # 2. Fallback Mechanism: If the thumbnail fails or is too small, fetch the raw original image
        if img_res is None or img_res.status_code != 200 or len(img_res.content) < 10000:
            print("   ⚠️ 1920px thumbnail failed or is too small. Attempting original full-size image fallback...")
            img_res = safe_get(base_image_url, headers=DOWNLOAD_HEADERS, timeout=30)
        
        # 3. Comprehensive Error Checking
        if img_res is None:
            print("   ❌ Network completely failed to connect to Wikimedia Commons.")
        elif img_res.status_code != 200:
            print(f"   ❌ Wikimedia Image CDN rejected the request (HTTP {img_res.status_code}).")
        elif len(img_res.content) < 10000:
            print(f"   ❌ Downloaded file is too small ({len(img_res.content)} bytes). Image likely corrupted or protected.")
        else:
            success = stamp_image(img_res.content, painting_meta, image_filename)
            
            if success:
                print(f"✅ Successfully stamped and saved as {image_filename}")
                new_entry = {
                    "title": f"{painting_meta['title']} by {painting_meta['artist']}",
                    "image_url": f"{GITHUB_PAGES_URL}/{image_filename}",
                    "year": painting_meta['year'],
                    "museum": painting_meta['museum'],
                    "description": ollama_review.get("description", "")
                }
                artwork_list.append(new_entry)
                seen_titles.add(normalize_title(painting_meta['title']))
                
                # Save progress
                save_json_file({"artwork_list": artwork_list}, "feed.json")
                current_count += 1
                next_file_number += 1 # Progress file tracking forward sequentially
                
                if current_count % 25 == 0:
                    push_to_github()
        
        time.sleep(DELAY_BETWEEN_DOWNLOADS)
        
    print("\n🎉 BULK COLLECTION COMPLETE!")
    push_to_github()

if __name__ == "__main__":
    try:
        run_bulk_collector()
    except KeyboardInterrupt:
        print("\n🛑 Manual stop detected. Progress safely saved.")