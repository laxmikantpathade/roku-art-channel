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
DELAY_BETWEEN_DOWNLOADS = 8  # Safe pacing for Wikidata rate limits

API_HEADERS = {
    "User-Agent": "RokuArtChannel/2.0 (https://laxmikantpathade.com; lpathade@example.com) Python-requests/2.31"
}

DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "image/jpeg,image/png,image/webp,*/*;q=0.8"
}

# --- TARGETED SPECIFIC MASTERPIECES CHECKLIST ---
TARGET_MASTERPIECES = [
    {"title": "Adoration of the Magi", "artist": "Gentile da Fabriano", "museum": "Uffizi Gallery, Florence", "year": "1423"},
    {"title": "Annunciation", "artist": "Leonardo da Vinci", "museum": "Uffizi Gallery, Florence", "year": "1475"},
    {"title": "The Garden of Earthly Delights", "artist": "Hieronymus Bosch", "museum": "Museo del Prado, Madrid", "year": "1490"},
    {"title": "Portrait of a Young Man", "artist": "Raphael", "museum": "Czartoryski Museum (Missing)", "year": "1514"},
    {"title": "The Wedding Feast at Cana", "artist": "Paolo Veronese", "museum": "Musée du Louvre, Paris", "year": "1563"},
    {"title": "The Hunters in the Snow", "artist": "Pieter Bruegel the Elder", "museum": "Kunsthistorisches Museum, Vienna", "year": "1565"},
    {"title": "Vista de Toledo", "artist": "El Greco", "museum": "Museo de El Greco, Toledo", "year": "1596"},
    {"title": "Supper at Emmaus", "artist": "Caravaggio", "museum": "National Gallery, London", "year": "1601"},
    {"title": "Susanna and the Elders", "artist": "Artemisia Gentileschi", "museum": "Schloss Weißenstein, Pommersfelden", "year": "1610"},
    {"title": "The Storm on the Sea of Galilee", "artist": "Rembrandt", "museum": "Isabella Stewart Gardner Museum (Stolen)", "year": "1633"},
    {"title": "The Syndics of the Draper's Guild", "artist": "Rembrandt", "museum": "Rijksmuseum, Amsterdam", "year": "1662"},
    {"title": "The Astronomer", "artist": "Johannes Vermeer", "museum": "Musée du Louvre, Paris", "year": "1668"},
    {"title": "The Skater", "artist": "Gilbert Stuart", "museum": "National Gallery of Art, Washington D.C.", "year": "1782"},
    {"title": "The Third of May 1808", "artist":"Francisco Goya", "museum": "Museo del Prado, Madrid", "year": "1814"},
    {"title": "The Hireling Shepherd", "artist": "William Holman Hunt", "museum": "Manchester Art Gallery", "year": "1851"},
    {"title": "Washington Crossing the Delaware", "artist": "Emanuel Leutze", "museum": "Metropolitan Museum of Art, New York", "year": "1851"},
    {"title": "The Gleaners", "artist": "Jean-François Millet", "museum": "Musée d'Orsay, Paris", "year": "1857"},
    {"title": "Olympia", "artist": "Édouard Manet", "museum": "Musée d'Orsay, Paris", "year": "1863"},
    {"title": "Pollice Verso", "artist": "Jean-Léon Gérôme", "museum": "Phoenix Art Museum, Phoenix", "year": "1872"},
    {"title": "Breezing Up", "artist": "Winslow Homer", "museum": "National Gallery of Art, Washington D.C.", "year": "1876"},
    {"title": "The Bath", "artist": "Jean-Léon Gérôme", "museum": "Fine Arts Museums of San Francisco", "year": "1885"},
    {"title": "The Lady of Shalott", "artist": "John William Waterhouse", "museum": "Tate Britain, London", "year": "1888"},
    {"title": "The Night Café", "artist": "Vincent van Gogh", "museum": "Yale University Art Gallery, New Haven", "year": "1888"},
    {"title": "The Wave", "artist": "William-Adolphe Bouguereau", "museum": "Private Collection", "year": "1896"},
    {"title": "Le Boulevard de Montmartre, Matinée de Printemps", "artist": "Camille Pissarro", "museum": "Private Collection", "year": "1897"},
    {"title": "The Kiss", "artist": "Edvard Munch", "museum": "Munch-museet, Oslo", "year": "1897"},
    {"title": "Water Lilies and Japanese Bridge", "artist": "Claude Monet", "museum": "Princeton University Art Museum", "year": "1899"},
    {"title": "Portrait of Adele Bloch-Bauer I", "artist": "Gustav Klimt", "museum": "Neue Galerie, New York", "year": "1907"},
    {"title": "The Kiss", "artist": "Gustav Klimt", "museum": "Österreichische Galerie Belvedere, Vienna", "year": "1908"},
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

def safe_get(url, headers=None, params=None, timeout=15):
    try:
        res = requests.get(url, headers=headers, params=params, timeout=timeout)
        return res
    except Exception as e:
        print(f"   ⚠️ Connection tracking hiccup: {e}")
        return None

def get_next_available_index(folder="."):
    """Scans folder to find the highest existing image_X.jpg sequence."""
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

# --- OPTIMIZED WIKIDATA QUERY RESOLUTION ENGINE ---

def search_specific_masterpiece_image(title, artist):
    """Searches Wikidata by title alone, then handles flexible artist filtering."""
    print(f"   🌐 Querying Wikidata lookup engine for title: '{title}'...")
    
    search_params = {
        "action": "wbsearchentities",
        "search": title,  # Search exclusively by title to circumvent label constraints
        "language": "en",
        "format": "json",
        "limit": 10       # Scan top matches
    }
    res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=search_params)
    if not res or not res.json().get('search'):
        return None
        
    # Standardize artist string keywords into low-complexity parts (e.g. ['edward', 'hopper'])
    artist_keywords = [w.lower() for w in re.findall(r'\w+', artist) if len(w) > 2]
    
    for hit in res.json()['search']:
        qid = hit['id']
        label = hit.get('label', '').lower()
        description = hit.get('description', '').lower()
        
        # Verify if hit corresponds to a painting/artwork entry by matching keywords
        artist_match = any(word in description or word in label for word in artist_keywords)
        is_painting_context = any(term in description for term in ["painting", "mural", "artwork", "canvas", "fresco"])
        
        if artist_match or (normalize_title(hit.get('label', '')) == normalize_title(title) and is_painting_context):
            # Target property P18 image values across the verified entity leaf
            sparql_query = f"""
            SELECT ?image WHERE {{
              wd:{qid} wdt:P18 ?image.
            }}
            """
            headers = {"Accept": "application/sparql-results+json", **API_HEADERS}
            s_res = safe_get("https://query.wikidata.org/sparql", headers=headers, params={'query': sparql_query})
            if s_res:
                bindings = s_res.json().get('results', {}).get('bindings', [])
                if bindings:
                    img_url = bindings[0].get('image', {}).get('value', '')
                    if img_url:
                        return img_url
                        
    return None

def push_to_github():
    print("\n🚀 Pushing priority checklist batch synchronization to GitHub...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "🤖 Target checklist processing complete via 2K padded engine"], check=True)
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
            continue  # Avoid duplication if already inside database tracking array
            
        print(f"\n🎯 Target Match isolated: '{target['title']}' by {target['artist']}")
        image_url = search_specific_masterpiece_image(target["title"], target["artist"])
        
        if not image_url:
            print("   ❌ Image asset resource pointer not initialized on Wikidata. Skipping row.")
            continue
            
        image_filename = f"image_{next_file_number}.jpg"
        download_url = f"{image_url}?width=2560"  # Target 2K asset bucket directly
        
        img_res = safe_get(download_url, headers=DOWNLOAD_HEADERS, timeout=20)
        if img_res is None or img_res.status_code != 200 or len(img_res.content) < 10000:
            print("   ⚠️ 2560px profile rejected. Falling back to source raw payload wrapper...")
            img_res = safe_get(image_url, headers=DOWNLOAD_HEADERS, timeout=30)
            
        if img_res and img_res.status_code == 200 and len(img_res.content) >= 10000:
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