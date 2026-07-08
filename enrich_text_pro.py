import os
import json
import time
import re
import base64
import requests
import wikipedia
import warnings
from PIL import Image
from io import BytesIO

# --- FORCE SUPPRESS MAC LIBRESSL/URLLIB3 WARNINGS ---
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", module="urllib3")

FEED_FILE = "feed.json"
VISION_MODEL = "llava"  

# Set a compliant User-Agent header for Wikipedia
wikipedia.set_user_agent("RokuArtChannelProject/2.0 (lpathade@example.com)")

def fetch_wikipedia_context(title, artist):
    """Queries Wikipedia for both the artwork and the artist."""
    artwork_text = ""
    artist_text = ""
    
    # Don't waste time querying generic placeholder titles
    if title.lower() in ["untitled", "arab", "study", "portrait", "landscape", "unknown"]:
        print(f"   [text_search] 🏷️ Title '{title}' is generic. Bypassing specific artwork wiki search.")
        search_queries = [f"{artist} painting", artist]
    else:
        search_queries = [f"{title} ({artist} painting)", f"{title} (painting)", f"{title} {artist}"]

    for query in search_queries:
        try:
            print(f"   [text_search] 🔍 Querying Wikipedia for: '{query}'...")
            artwork_text = wikipedia.summary(query, sentences=4) 
            if artwork_text:
                print(f"   [text_search] ✅ Found dedicated Wikipedia entry for this artwork.")
                break
        except (wikipedia.exceptions.PageError, wikipedia.exceptions.DisambiguationError):
            continue
        except Exception:
            break
            
    try:
        print(f"   [text_search] 🔍 Querying Wikipedia for artist bio: '{artist}'...")
        artist_text = wikipedia.summary(artist, sentences=4)
        if artist_text:
            print(f"   [text_search] ✅ Found artist biography text.")
    except Exception:
        print(f"   [text_search] ⚠️ No specific bio text returned for '{artist}'.")
        pass
        
    return artwork_text, artist_text

def encode_optimized_thumbnail(image_path):
    """Opens the 2K file, scales it down to model-native resolution for VRAM safety."""
    if os.path.exists(image_path):
        try:
            print(f"   [image_prep] 📂 Opening master high-res file: {image_path}")
            with Image.open(image_path) as img:
                orig_w, orig_h = img.size
                
                # Downsample to common vision model input size (keeps original file safe on disk)
                print(f"   [image_prep] ⚡ Downscaling raw canvas from {orig_w}x{orig_h} to safe 448px bounding box...")
                img.thumbnail((448, 448), Image.Resampling.LANCZOS)
                
                buffered = BytesIO()
                img.convert("RGB").save(buffered, format="JPEG", quality=75)
                
                print(f"   [image_prep] 🔒 Compressing payload into a memory-safe Base64 string.")
                return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"   [image_prep] ❌ Image optimization failed for {image_path}: {e}")
    return None

def request_ollama_multimodal(title, artist, year, museum, artwork_context, artist_context, base64_image):
    """Sends the metadata, Wikipedia text, AND image to Ollama with a strict 80/20 data priority split."""
    
    system_instructions = (
        "You are an elite, academic art history professor and master museum curator.\n"
        "You are reviewing verified historical texts while referencing an image of the artwork.\n"
        "Your task is to write a highly sophisticated, technical, and engaging catalog entry for this artwork.\n"
        "CRITICAL FORMATTING RULES:\n"
        "1. Target length: STRICTLY around 180 to 220 words.\n"
        "2. DO NOT state or repeat the artwork title, artist name, year, or museum in the text—it is already hardcoded on screen.\n"
        "3. DO NOT use generic introductory fluff like 'This painting is...' or 'Created in 1880...'. Jump immediately into the analysis.\n"
        "4. BAN ALL GENERIC FLUFF about 'appreciated by the masses', 'timeless masterpiece', or 'captivates viewers' UNLESS the image is an undisputed world-famous superstar (e.g., Mona Lisa, Starry Night).\n"
        "5. Respond with ONLY the raw text description. No conversational filler, no introductions, no formatting marks."
    )
    
    prompt = (
        f"Artwork Details:\n"
        f"- Title: {title}\n"
        f"- Artist: {artist}\n"
        f"- Year: {year}\n"
        f"- Location: {museum}\n\n"
        f"--- PRIMARY DATA SOURCE: WIKIPEDIA ARTIST CONTEXT ---\n{artist_context}\n\n"
        f"--- PRIMARY DATA SOURCE: WIKIPEDIA ARTWORK CONTEXT ---\n{artwork_context}\n\n"
        f"DATA PROCESSING WEIGHTS & CRITERIA:\n"
        f"- Sentence 1: Provide exactly ONE profound sentence summarizing the artist's overall historical art background, stylistic movement, and legacy based on the data.\n"
        f"- IF THE WIKIPEDIA ARTWORK DATA IS POPULATED:\n"
        f"  * Apply an 80% weight to the Wikipedia text context. The overarching themes, specific historical background, academic analysis, and provenance found in the text MUST dictate the entire core of your review.\n"
        f"  * Apply a 20% weight to the attached image. Use your visual sight of the image purely as a secondary reference to verify, confirm, and ground the textual claims (e.g., matching the specific lighting, palettes, layout, or brushstrokes detailed in the text to the actual image file).\n"
        f"- IF THE WIKIPEDIA ARTWORK DATA IS EMPTY OR GENERIC (e.g., 'Untitled', 'Arab'):\n"
        f"  * Shift the weights entirely to a pure visual critique of the attached image (composition, lighting, values, textures). Interpret these visual discoveries strictly through the lens of the artist's known historical background and period conventions."
    )

    payload = {
        "model": VISION_MODEL, 
        "prompt": f"{system_instructions}\n\n{prompt}", 
        "stream": False,
        "options": {"temperature": 0.4, "num_predict": 450}
    }

    if base64_image:
        payload["images"] = [base64_image]

    try:
        print(f"   [ollama_core] 🧠 Dispatching fusion payload to local '{VISION_MODEL}' instance. Processing...")
        start_time = time.time()
        
        response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=180)
        
        elapsed = time.time() - start_time
        if response.status_code == 200:
            print(f"   [ollama_core] ✨ Generation finished successfully in {elapsed:.2f} seconds.")
            return response.json().get("response", "").strip()
        else:
            print(f"   [ollama_core] ❌ Ollama rejected request with HTTP status: {response.status_code}")
    except Exception as e:
        print(f"   [ollama_core] ❌ Network timeout or exception during model run: {e}")
    return None

def enrich_catalog():
    if not os.path.exists(FEED_FILE):
        print(f"❌ Error: {FEED_FILE} not found!")
        return

    with open(FEED_FILE, "r") as f:
        feed_data = json.load(f)
        
    artwork_list = feed_data.get("artwork_list", [])
    total = len(artwork_list)
    print(f"🚀 Initializing Clean Start Multimodal Vision Enhancer for {total} files...")

    for idx, art in enumerate(artwork_list):
        full_title = art.get("title", "")
        if " by " in full_title:
            title = full_title.rsplit(" by ", 1)[0]
            artist = full_title.rsplit(" by ", 1)[1]
        else:
            title = full_title
            artist = "Unknown Artist"
            
        filename = art.get("image_url", "").split("/")[-1]
        
        # NOTE: Safety skip check is intentionally forced open (commented out) 
        # to ensure the script begins exactly at image_1.jpg onwards.
        # current_desc = art.get("description", "")
        # if len(current_desc) > 50 and "Historical masterpiece entry" not in current_desc:
        #     continue
            
        print(f"\n================================================================================")
        print(f"👁️  [{idx + 1}/{total}] BEGINNING PROCESSING PIPELINE FOR: {filename}")
        print(f"   📋 Metadata Profile: '{title}' | Artist: {artist} | Year: {art.get('year','?')}")
        print(f"================================================================================")
        
        # 1. Fetch Wikipedia text
        artwork_context, artist_context = fetch_wikipedia_context(title, artist)
        
        # Determine and log strategy prior to generation
        if artwork_context:
            print("   [pipeline_strategy] 🎯 STRATEGY: Wikipedia text found. Setting priority weights to 80% Text / 20% Visual Confirmation.")
        else:
            print("   [pipeline_strategy] 🎨 STRATEGY: Wikipedia text empty. Setting priority weights to 100% Computer Vision Contextual Fallback.")
        
        # 2. Encode optimized micro-thumbnail
        base64_image = encode_optimized_thumbnail(filename)
        if not base64_image:
            print(f"   ⚠️ Could not optimize or locate local file '{filename}'. Skipping image sight.")
            
        # 3. Request description
        enhanced_description = request_ollama_multimodal(
            title, artist, art.get("year", ""), art.get("museum", ""), 
            artwork_context, artist_context, base64_image
        )
        
        if enhanced_description:
            art["description"] = enhanced_description
            print(f"   📝 Successfully saved entry ({len(enhanced_description.split())} words).")
            
            with open(FEED_FILE, "w") as f:
                json.dump(feed_data, f, indent=4)
        else:
            print("   ❌ Generation cycle failed for this asset. Leaving old text entry intact.")
            
        # System rest gap to clear garbage collection cycles safely
        print(f"   [cooldown] 💤 Pausing for 3 seconds to clear Mac hardware VRAM cycles...")
        time.sleep(3)

    print("\n🎉 CATALOG TEXT ENRICHMENT COMPLETE!")

if __name__ == "__main__":
    enrich_catalog()