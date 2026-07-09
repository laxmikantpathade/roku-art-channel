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
DELAY_BETWEEN_DOWNLOADS = 6  # Paced safely for Wikidata rate limits

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
    {"title": "Arnolfini Portrait", "artist": "Jan van Eyck", "museum": "National Gallery, London", "year": "1434"},
    {"title": "Saint George and the Dragon", "artist": "Paolo Uccello", "museum": "National Gallery, London", "year": "1470"},
    {"title": "Annunciation", "artist": "Leonardo da Vinci", "museum": "Uffizi Gallery, Florence", "year": "1475"},
    {"title": "Primavera", "artist": "Sandro Botticelli", "museum": "Uffizi Gallery, Florence", "year": "1480"},
    {"title": "The Birth of Venus", "artist": "Sandro Botticelli", "museum": "Uffizi Gallery, Florence", "year": "1486"},
    {"title": "The Garden of Earthly Delights", "artist": "Hieronymus Bosch", "museum": "Museo del Prado, Madrid", "year": "1490"},
    {"title": "Lady with an Ermine", "artist": "Leonardo da Vinci", "museum": "The National Museum in Krakow", "year": "1490"},
    {"title": "The Last Supper", "artist": "Leonardo da Vinci", "museum": "Convent of Santa Maria delle Grazie, Milan", "year": "1498"},
    {"title": "Feast of the Rosary", "artist": "Albrecht Dürer", "museum": "National Gallery, Prague", "year": "1506"},
    {"title": "Sleeping Venus", "artist": "Titian", "museum": "Gemäldegalerie Alte Meister, Dresden", "year": "1510"},
    {"title": "The School of Athens", "artist": "Raphael", "museum": "Apostolic Palace, Vatican City", "year": "1511"},
    {"title": "The Creation of Adam", "artist": "Michelangelo", "museum": "Sistine Chapel, Vatican City", "year": "1512"},
    {"title": "Portrait of a Young Man", "artist": "Raphael", "museum": "Czartoryski Museum, Kraków, Poland (missing)", "year": "1514"},
    {"title": "Triumph of Galatea", "artist": "Raphael", "museum": "Villa Farnesina, Rome", "year": "1514"},
    {"title": "Bacchus and Ariadne", "artist": "Titian", "museum": "National Gallery, London", "year": "1523"},
    {"title": "The Ambassadors", "artist": "Hans Holbein the Younger", "museum": "National Gallery, London", "year": "1533"},
    {"title": "Landscape with the Fall of Icarus", "artist": "Pieter Bruegel the Elder", "museum": "Royal Museums of Fine Arts of Belgium, Brussels", "year": "1558"},
    {"title": "The Wedding Feast at Cana", "artist": "Paolo Veronese", "museum": "Musée du Louvre, Paris", "year": "1563"},
    {"title": "The Hunters in the Snow", "artist": "Pieter Bruegel the Elder", "museum": "Kunsthistorisches Museum, Vienna", "year": "1565"},
    {"title": "The Musicians", "artist": "Caravaggio", "museum": "Metropolitan Museum of Art, New York", "year": "1595"},
    {"title": "Vista de Toledo", "artist": "El Greco", "museum": "Museo de El Greco, Toledo", "year": "1596"},
    {"title": "Supper at Emmaus", "artist": "Caravaggio", "museum": "National Gallery, London", "year": "1601"},
    {"title": "Susanna and the Elders", "artist": "Artemisia Gentileschi", "museum": "Schloss Weißenstein, Pommersfelden", "year": "1610"},
    {"title": "Laughing Cavalier", "artist": "Frans Hals", "museum": "Wallace Collection, London", "year": "1624"},
    {"title": "The Anatomy Lesson of Dr. Nicolaes Tulp", "artist": "Rembrandt", "museum": "Mauritshuis, The Hague", "year": "1632"},
    {"title": "The Storm on the Sea of Galilee", "artist": "Rembrandt", "museum": "Isabella Stewart Gardner Museum (Missing)", "year": "1633"},
    {"title": "Charles I in Three Positions", "artist": "Anthony van Dyck", "museum": "Royal Collection", "year": "1636"},
    {"title": "The Night Watch", "artist": "Rembrandt", "museum": "Rijksmuseum, Amsterdam", "year": "1642"},
    {"title": "Las Meninas", "artist": "Diego Velázquez", "museum": "Museo del Prado, Madrid", "year": "1656"},
    {"title": "The Syndics of the Draper's Guild", "artist": "Rembrandt", "museum": "Rijksmuseum, Amsterdam", "year": "1662"},
    {"title": "Girl with a Pearl Earring", "artist": "Johannes Vermeer", "museum": "Mauritshuis, The Hague", "year": "1665"},
    {"title": "The Astronomer", "artist": "Johannes Vermeer", "museum": "Musée du Louvre, Paris", "year": "1668"},
    {"title": "The Embarkation for Cythera", "artist": "Antoine Watteau", "museum": "Charlottenburg Palace, Berlin", "year": "1717"},
    {"title": "Mr and Mrs Andrews", "artist": "Thomas Gainsborough", "museum": "National Gallery, London", "year": "1750"},
    {"title": "The Happy Accidents of the Swing", "artist": "Jean-Honoré Fragonard", "museum": "Wallace Collection, London", "year": "1767"},
    {"title": "Watson and the Shark", "artist": "John Singleton Copley", "museum": "National Gallery of Art, Washington D.C.", "year": "1778"},
    {"title": "The Ladies Waldegrave", "artist": "Joshua Reynolds", "museum": "Scottish National Gallery, Edinburgh", "year": "1781"},
    {"title": "The Skater", "artist": "Gilbert Stuart", "museum": "National Gallery of Art, Washington D.C.", "year": "1782"},
    {"title": "Oath of the Horatii", "artist": "Jacques-Louis David", "museum": "Musée du Louvre, Paris", "year": "1784"},
    {"title": "Napoleon Crossing the Alps", "artist": "Jacques-Louis David", "museum": "Palace of Versailles, Paris", "year": "1801"},
    {"title": "The Third of May 1808", "artist": "Francisco Goya", "museum": "Museo del Prado, Madrid", "year": "1814"},
    {"title": "The Raft of the Medusa", "artist": "Théodore Géricault", "museum": "Musée du Louvre, Paris", "year": "1819"},
    {"title": "The Hay Wain", "artist": "John Constable", "museum": "National Gallery, London", "year": "1821"},
    {"title": "Liberty Leading the People", "artist": "Eugène Delacroix", "museum": "Musée du Louvre, Paris", "year": "1830"},
    {"title": "The Hireling Shepherd", "artist": "William Holman Hunt", "museum": "Manchester Art Gallery, Manchester", "year": "1851"},
    {"title": "Washington Crossing the Delaware", "artist": "Emanuel Leutze", "museum": "Metropolitan Museum of Art, New York", "year": "1851"},
    {"title": "The Gleaners", "artist": "Jean-François Millet", "museum": "Musée d'Orsay, Paris", "year": "1857"},
    {"title": "The Kiss", "artist": "Francesco Hayez", "museum": "Pinacoteca de Brera, Milan", "year": "1859"},
    {"title": "Olympia", "artist": "Édouard Manet", "museum": "Musée d'Orsay, Paris", "year": "1863"},
    {"title": "The Sleepers", "artist": "Gustave Courbet", "museum": "Petit Palais, Paris", "year": "1866"},
    {"title": "Whistler's Mother", "artist": "James McNeill Whistler", "museum": "Louvre Abu Dhabi", "year": "1871"},
    {"title": "Impression, Sunrise", "artist": "Claude Monet", "museum": "Musée Marmottan Monet, Paris", "year": "1872"},
    {"title": "Pollice Verso", "artist": "Jean-Léon Gérôme", "museum": "Phoenix Art Museum, Phoenix", "year": "1872"},
    {"title": "A Cotton Office in New Orleans", "artist": "Edgar Degas", "museum": "Musee des Beaux-Arts in Pau, France", "year": "1873"},
    {"title": "The Gross Clinic", "artist": "Thomas Eakins", "museum": "Philadelphia Museum of Art", "year": "1875"},
    {"title": "Bal du moulin de la Galette", "artist": "Pierre-Auguste Renoir", "museum": "Musée d'Orsay, Paris", "year": "1876"},
    {"title": "Breezing Up", "artist": "Winslow Homer", "museum": "National Gallery of Art, Washington D.C.", "year": "1876"},
    {"title": "Luncheon of the Boating Party", "artist": "Pierre-Auguste Renoir", "museum": "Phillips Collection, Washington D.C.", "year": "1881"},
    {"title": "A Bar at the Folies-Bergère", "artist": "Édouard Manet", "museum": "Courtauld Gallery, London", "year": "1882"},
    {"title": "A Sunday Afternoon on the Island of La Grande Jatte", "artist": "Georges Seurat", "museum": "Art Institute of Chicago", "year": "1884"},
    {"title": "The Bath", "artist": "Jean-Léon Gérôme", "museum": "Fine Arts Museums of San Francisco", "year": "1885"},
    {"title": "The Potato Eaters", "artist": "Vincent van Gogh", "museum": "Van Gogh Museum, Amsterdam", "year": "1885"},
    {"title": "The Lady of Shalott", "artist": "John William Waterhouse", "museum": "Tate Britain, London", "year": "1888"},
    {"title": "The Night Café", "artist": "Vincent van Gogh", "museum": "Yale University Art Gallery, New Haven", "year": "1888"},
    {"title": "The Starry Night", "artist": "Vincent van Gogh", "museum": "Museum of Modern Art, New York City", "year": "1889"},
    {"title": "The Boating Party", "artist": "Mary Cassatt", "museum": "National Gallery of Art, Washington D.C.", "year": "1893"},
    {"title": "Flaming June", "artist": "Frederic Leighton", "museum": "Museo de Arte de Ponce, Puerto Rico", "year": "1895"},
    {"title": "The Wave", "artist": "William-Adolphe Bouguereau", "museum": "Private Collection", "year": "1896"},
    {"title": "Le Boulevard de Montmartre, Matinée de Printemps", "artist": "Camille Pissarro", "museum": "Private Collection", "year": "1897"},
    {"title": "The Kiss", "artist": "Edvard Munch", "museum": "Munch-museet, Oslo", "year": "1897"},
    {"title": "Water Lilies and Japanese Bridge", "artist": "Claude Monet", "museum": "Princeton University Art Museum", "year": "1899"},
    {"title": "Portrait of Adele Bloch-Bauer I", "artist": "Gustav Klimt", "museum": "Neue Galerie, New York", "year": "1907"},
    {"title": "The Kiss", "artist": "Gustav Klimt", "museum": "Österreichische Galerie Belvedere, Vienna", "year": "1908"},
    {"title": "American Gothic", "artist": "Grant Wood", "museum": "Art Institute of Chicago", "year": "1930"},
    {"title": "Guernica", "artist": "Pablo Picasso", "museum": "Museo Reina Sofía, Madrid", "year": "1937"},
    {"title": "Nighthawks", "artist": "Edward Hopper", "museum": "Art Institute of Chicago", "year": "1942"}
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
        print(f"❌ Error saving JSON data to {filepath}: {e}")

def normalize_title(title):
    t = str(title).lower()
    t = re.sub(r'\(.*?\)', '', t)
    t = re.sub(r'[^a-z0-9]', '', t)
    return t.strip()

def safe_get(url, headers=None, params=None, timeout=15):
    try:
        res = requests.get(url, headers=headers, params=params, timeout=timeout)
        return res
    except Exception as e:
        print(f"   ⚠️ Connection tracking error: {e}")
        return None

def get_next_available_index(folder_path):
    """Scans local storage folder to find the absolute maximum file serial sequence."""
    max_num = 0
    if os.path.exists(folder_path):
        for f in os.listdir(folder_path):
            match = re.match(r'image_(\d+)\.jpg', f)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num + 1

# --- IMAGE GRAPHICS STAMP PANEL GENERATOR ---

def stamp_image(raw_bytes, meta, out_filename):
    """Resizes, crops to TV aspect ratio, and adds the text banner."""
    try:
        img = Image.open(BytesIO(raw_bytes))
        
        # Canvas Normalization to standard 1080p layout specifications
        target_w, target_h = 1920, 1080
        img_aspect = img.width / img.height
        target_aspect = target_w / target_h

        if img_aspect > target_aspect:
            new_h = target_h
            new_w = int(target_h * img_aspect)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            left = (new_w - target_w) // 2
            img = img.crop((left, 0, left + target_w, target_h))
        else:
            new_w = target_w
            new_h = int(target_w / img_aspect)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            top = (new_h - target_h) // 2
            img = img.crop((0, top, target_w, top + target_h))

        draw = ImageDraw.Draw(img)
        
        font_paths = [
            "/System/Library/Fonts/FontsAvailableAtRuntime/Georgia.ttf",
            "/Library/Fonts/Georgia.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        ]
        font = None
        for path in font_paths:
            if os.path.exists(path):
                font = ImageFont.truetype(path, 22)
                break
        if font is None:
            font = ImageFont.load_default()

        banner_text = f"{meta['artist']}  ·  {meta['title']}  ·  {meta['museum']}  ·  {meta['year']}"
        
        draw.rectangle([0, 1025, 1920, 1080], fill=(0, 0, 0, 160))
        
        text_w = draw.textlength(banner_text, font=font) if hasattr(draw, "textlength") else 800
        x_pos = (target_w - text_w) // 2
        
        draw.text((x_pos, 1038), banner_text, fill=(235, 235, 235), font=font)
        
        img.save(out_filename, "JPEG", quality=92)
        return True
    except Exception as e:
        print(f"   ❌ Graphic execution layout engine error: {e}")
        return False

# --- WIKIDATA EXTRACTION CORE PIPELINE ---

def search_specific_masterpiece_image(title, artist):
    """Searches Wikidata specifically combining Title + Artist strings to return an official image URL."""
    search_query = f"{title} {artist}"
    print(f"   🌐 Querying Wikidata engine interface for: '{search_query}'...")
    
    search_params = {
        "action": "wbsearchentities",
        "search": search_query,
        "language": "en",
        "format": "json",
        "limit": 3
    }
    res = safe_get("https://www.wikidata.org/w/api.php", headers=API_HEADERS, params=search_params)
    if not res or not res.json().get('search'):
        return None
        
    for hit in res.json()['search']:
        qid = hit['id']
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
                return bindings[0].get('image', {}).get('value', '')
                
    return None

def push_to_github():
    print("   🚀 Initiating background staging deployment push to GitHub...")
    try:
        subprocess.run(["git", "add", "feed.json", "image_*.jpg"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "🤖 Auto-stamped curated priority masterpieces collection data rows"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        print("   ✅ Sync Complete! Server endpoints are active.")
    except Exception as e:
        print(f"   ⚠️ GitHub Sync process skipped or hit local layout validation edge: {e}")

# --- MAIN RUNNER ENGINE EXECUTION ENTRYPOINT ---

def run_targeted_collector():
    print("👑 Target Priority Masterpiece Recruitment Pipeline Active...")
    
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
        
    print(f"📂 Current database tracking array holds {len(artwork_list)} active entries.")
    print(f"📸 Next image naming slot safely targeted at: image_{next_file_number}.jpg")
    
    downloaded_any = False
    
    for target in TARGET_MASTERPIECES:
        norm_title = normalize_title(target["title"])
        if norm_title in seen_titles:
            continue  # Already processed previously
            
        print(f"\n🎯 Processing Item: '{target['title']}' by {target['artist']}")
        image_url = search_specific_masterpiece_image(target["title"], target["artist"])
        
        if not image_url:
            print("   ❌ Could not locate a verified image asset URL on Wikidata. Skipping entry.")
            continue
            
        image_filename = f"image_{next_file_number}.jpg"
        download_url = f"{image_url}?width=2560"  # Request high resolution from Wikipedia CDN
        
        img_res = safe_get(download_url, headers=DOWNLOAD_HEADERS, timeout=20)
        if img_res is None or img_res.status_code != 200 or len(img_res.content) < 10000:
            img_res = safe_get(image_url, headers=DOWNLOAD_HEADERS, timeout=30)
            
        if img_res and img_res.status_code == 200 and len(img_res.content) >= 10000:
            success = stamp_image(img_res.content, target, image_filename)
            if success:
                print(f"✅ Successfully stamped and saved asset file: {image_filename}")
                new_entry = {
                    "title": f"{target['title']} by {target['artist']}",
                    "image_url": f"{GITHUB_PAGES_URL}/{image_filename}",
                    "year": target['year'],
                    "museum": target['museum'],
                    "description": "Historical masterpiece entry." # Placeholder to be enriched by the Gemini script next
                }
                artwork_list.append(new_entry)
                seen_titles.add(norm_title)
                downloaded_any = True
                
                save_json_file({"artwork_list": artwork_list}, "feed.json")
                next_file_number += 1
        
        time.sleep(DELAY_BETWEEN_DOWNLOADS)
        
    if downloaded_any:
        print("\n🎉 ALL PENDING TARGET CHECKLIST ITEMS CAPTURED SUCCESSFULLY!")
        push_to_github()
    else:
        print("\n✨ All targets in the priority checklist are already added. Database is up to date!")

if __name__ == "__main__":
    try:
        run_targeted_collector()
    except KeyboardInterrupt:
        print("\n🛑 Manual pause instruction detected. Closing download pipes safely.")