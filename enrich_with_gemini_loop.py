import os
import json
import time
import re
import requests
import wikipedia
import warnings
import base64
from PIL import Image

# --- SUPPRESS WARNINGS ---
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", module="urllib3")

FEED_FILE = "feed.json"
OLLAMA_CRITIC_MODEL = "llama3.2"  

# Target the lightning-fast 3.1 lite model
FREE_MODEL = "gemini-3.1-flash-lite"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{FREE_MODEL}:generateContent?key={GEMINI_API_KEY}"

wikipedia.set_user_agent("RokuArtChannelProject/2.0 (lpathade@example.com)")

def fetch_wikipedia_context(title, artist):
    """Queries Wikipedia for historical data."""
    artwork_text, artist_text = "", ""
    if title.lower() in ["untitled", "arab", "study", "portrait", "landscape", "unknown"]:
        search_queries = [f"{artist} painting", artist]
    else:
        search_queries = [f"{title} ({artist} painting)", f"{title} (painting)", f"{title} {artist}"]

    for query in search_queries:
        try:
            artwork_text = wikipedia.summary(query, sentences=4)
            if artwork_text: break
        except Exception: continue
    try:
        artist_text = wikipedia.summary(artist, sentences=4)
    except Exception: pass
    return artwork_text, artist_text

def run_ollama_critic(description):
    """Simplified stylistic check. Hard logic rules are now processed via Python."""
    prompt = (
        f"You are an academic copyeditor. Review this text for tone:\n\n"
        f"\"\"\"{description}\"\"\"\n\n"
        f"Is the tone sophisticated, objective, and scholarly? "
        f"Does it completely avoid lazy promotional clichés like 'masterpiece', 'timeless', or 'captivates'?\n\n"
        f"If the text sounds like a proper academic entry, reply with exactly one word: PASSED\n"
        f"If it uses lazy marketing fluff, reply with: FAILED"
    )
    try:
        res = requests.post("http://localhost:11434/api/generate", 
                            json={"model": OLLAMA_CRITIC_MODEL, "prompt": prompt, "stream": False}, timeout=30)
        if res.status_code == 200:
            return res.json().get("response", "").strip()
    except Exception as e:
        print(f"   [critic] ⚠️ Ollama Critic unavailable ({e}). Defaulting to Pass.")
    return "PASSED"

def post_to_gemini_with_backoff(payload):
    """Safely extracts the text block and handles multi-tier rate limits with smart pacing."""
    while True:
        try:
            response = requests.post(GEMINI_URL, json=payload, timeout=60)
            res_json = response.json()
            
            if response.status_code == 200:
                try:
                    return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                except (KeyError, IndexError):
                    print("   [gemini_api] ⚠️ Structural layout shift. Extracting raw parts...")
                    try:
                        text_output = ""
                        for part in res_json['candidates'][0]['content']['parts']:
                            if 'text' in part:
                                text_output += part['text'] + "\n"
                        return text_output.strip()
                    except Exception:
                        return None
                
            elif response.status_code in [429, 503]:
                error_msg = res_json.get("error", {}).get("message", "")
                status = res_json.get("error", {}).get("status", "ERROR")
                
                if "Quota exceeded for quota daily" in error_msg or "Daily limit" in error_msg:
                    print("\n🛑 [CRITICAL] Hard Daily Credit Limit Exhausted!")
                    print("⏳ The script will sleep for 30 minutes before checking again, or you can kill the task with Ctrl+C.\n")
                    time.sleep(1800)
                    continue
                
                wait_seconds = 45
                retry_match = re.search(r'retry in ([\d\.]+)s', error_msg, re.IGNORECASE)
                if retry_match:
                    wait_seconds = int(float(retry_match.group(1))) + 2
                
                print(f"   [gemini_api] ⚠️ Server returned {response.status_code} ({status}).")
                print(f"   [gemini_api] ⏳ Free Tier Limit. Cooling down for {wait_seconds}s before retrying...")
                time.sleep(wait_seconds)
                continue
            else:
                print(f"   [gemini_api] ❌ Unexpected HTTP Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"   [gemini_api] ❌ Request Connection Error: {e}. Retrying in 10s...")
            time.sleep(10)

def encode_optimized_thumbnail(image_path):
    """Encodes a lightweight base64 JPEG payload to minimize API bandwidth usage."""
    if os.path.exists(image_path):
        try:
            with Image.open(image_path) as img:
                img.thumbnail((512, 512), Image.Resampling.LANCZOS)
                from io import BytesIO
                buffered = BytesIO()
                img.convert("RGB").save(buffered, format="JPEG", quality=80)
                return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception: pass
    return None

def generate_curated_description(title, artist, year, museum, artwork_context, artist_context, image_path):
    """Runs generation loop with programmatic checks for museum string leaks and token lengths."""
    if not GEMINI_API_KEY:
        print("   ❌ Error: GEMINI_API_KEY environment variable is not set!")
        return None
        
    system_instruction = (
        "You are an elite, academic art history professor and master museum curator. "
        "You write highly sophisticated, technical, and engaging catalog entries.\n"
        "CRITICAL RULES:\n"
        "1. Length MUST be strictly between 90 and 110 words (target exactly 100 words). No exceptions.\n"
        f"2. ALWAYS refer to the artist by their full name, '{artist}'. Never refer to them anonymously as 'the artist'.\n"
        f"3. You should smoothly incorporate the historical creation year ({year}) into the prose narrative.\n"
        f"4. NEVER mention the museum or collection name ('{museum}') anywhere in your text. Keep it completely absent.\n"
        "5. Never use introductory fluff (e.g., 'This painting is...'). Start directly with the analysis.\n"
        "6. BAN ALL GENERIC FLUFF ('timeless masterpiece', 'captivates viewers').\n"
        "7. Keep formatting tight: use a maximum of ONE paragraph break (newline) in your response."
    )
    
    base_prompt = (
        f"Context Details:\n- Title: {title}\n- Artist: {artist}\n- Year: {year}\n- Museum: {museum}\n\n"
        f"--- WIKIPEDIA ARTIST DATA ---\n{artist_context}\n\n"
        f"--- WIKIPEDIA ARTWORK DATA ---\n{artwork_context}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Structural Balance Requirement: Structure the narrative so roughly 20% of the text addresses {artist}'s historical movement background and significance. "
        f"The remaining 80% must focus heavily on the artwork itself, analyzing colors, composition, and visual execution.\n"
        f"- Title Handling: You may casually mention the title '{title}' within the analysis sentences if needed."
    )

    base64_image = encode_optimized_thumbnail(image_path)

    feedback = ""
    attempt = 1
    max_attempts = 5
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"}
    ]

    while attempt <= max_attempts:
        print(f"   [pipeline] 💡 Generation Attempt #{attempt} via Gemini [{FREE_MODEL}]...")
        
        if attempt == 1:
            current_prompt = base_prompt
        else:
            current_prompt = (
                f"{base_prompt}\n\n"
                f"⚠️ REWRITE REQUIREMENTS:\n{feedback}\n\n"
                f"Please completely rewrite the text. Target exactly 100 words."
            )
        
        parts = [{"text": current_prompt}]
        if base64_image:
            parts.insert(0, {
                "inlineData": {
                    "mimeType": "image/jpeg",
                    "data": base64_image
                }
            })
            
        payload = {
            "contents": [{"parts": parts}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "safetySettings": safety_settings,
            "generationConfig": {
                "temperature": 0.65, 
                "maxOutputTokens": 350
            }
        }
        
        draft = post_to_gemini_with_backoff(payload)
        if not draft:
            attempt += 1
            continue

        # Force the newline constraint mathematically via Python
        draft = draft.replace('\n\n', '\n')
        if draft.count('\n') > 1:
            sections = draft.split('\n')
            draft = sections[0] + '\n' + ' '.join(sections[1:])
            
        word_count = len(draft.split())
        print(f"   [pipeline] 📐 Extracted draft length: {word_count} words.")
        
        # 1. Programmatic Word Count Verification Guard (Clamped tightly around ~100)
        if word_count < 85 or word_count > 120:
            print(f"   [pipeline] ❌ Programmatic Rejected: Text length out of bounds ({word_count} words).")
            feedback = f"The generated text was {word_count} words. You MUST write between 90 and 110 words total."
            attempt += 1
            continue
            
        # 2. Programmatic Museum Content Injection Leak Detection Guard
        if museum and str(museum).lower() in draft.lower():
            print(f"   [pipeline] ❌ Programmatic Rejected: Museum leak detected ('{museum}').")
            feedback = f"CRITICAL LEAK: You included the name of the museum ('{museum}'). Rewrite the entry to remove any mention of the museum or collection."
            attempt += 1
            continue
            
        print("   [pipeline] 🔎 Passing text to local Ollama Copyeditor...")
        critic_verdict = run_ollama_critic(draft)
        
        if "PASSED" in critic_verdict.upper():
            print(f"   [pipeline] ✅ Text approved on attempt {attempt}!")
            return draft
        else:
            print(f"   [pipeline] ❌ Style Cop Rejected the draft tone.")
            feedback = "The style checker flag indicates the tone feels a bit flat or conversational. Elevate the historical vocabulary phrasing and ensure no fluff words exist."
            attempt += 1
            
    return draft

def enrich_catalog():
    if not os.path.exists(FEED_FILE): return
    with open(FEED_FILE, "r") as f:
        feed_data = json.load(f)
        
    artwork_list = feed_data.get("artwork_list", [])
    total = len(artwork_list)
    print(f"🚀 Starting FREE Multi-Agent Loop Controller for {total} files...")

    for idx, art in enumerate(artwork_list):
        
        # 👇 CHANGE THIS NUMBER TO RESUME PROCESSING FROM A DIFFERENT IMAGE INDEX
        # 0 = image_1, 1 = image_2, 99 = image_100, etc.
        if idx < 1509:
            continue

        full_title = art.get("title", "")
        title, artist = full_title.rsplit(" by ", 1) if " by " in full_title else (full_title, "Unknown Artist")
        filename = art.get("image_url", "").split("/")[-1]
        
        print(f"\n🎬 [{idx + 1}/{total}] Processing: {filename} ({title})")
        
        art_wiki, artist_wiki = fetch_wikipedia_context(title, artist)
        
        final_desc = generate_curated_description(
            title, artist, art.get("year", ""), art.get("museum", ""), 
            art_wiki, artist_wiki, filename
        )
        
        if final_desc:
            art["description"] = final_desc
            with open(FEED_FILE, "w") as f:
                json.dump(feed_data, f, indent=4)
            print(f"   💾 Saved polished entry ({len(final_desc.split())} words).")
            
        time.sleep(5) 

if __name__ == "__main__":
    enrich_catalog()