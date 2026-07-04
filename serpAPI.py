import os
import re
import requests

# --- CONFIGURATION ---
API_KEY = "b35602efdd748851f4be292c3be23365d561633e8c1e425be34edc08ee2990fe"  # Keep your SerpApi key here!

# 👇 Paste your raw GitHub folder path here (Make sure it ends with a slash / )
GITHUB_RAW_URL = "https://raw.githubusercontent.com/laxmikantpathade/roku-art-channel/main/" 

OUTPUT_FILE = "visual_lens_verification.txt"
MAX_FILES = 200

def get_sorted_art_files(folder):
    """Finds all existing files locally matching 'art_X.jpg' so we know what to ask GitHub for."""
    files = []
    for f in os.listdir(folder):
        if f.startswith("art_") and f.endswith(".jpg"):
            match = re.search(r'art_(\d+)\.jpg', f)
            if match:
                files.append((int(match.group(1)), f))
    files.sort(key=lambda x: x[0])
    return [f[1] for f in files]

def verify_images_visually():
    if API_KEY == "YOUR_ACTUAL_SERPAPI_KEY_HERE":
        print("❌ Error: Please provide your SerpApi key first.")
        return
        
    if "YourUsername" in GITHUB_RAW_URL:
        print("❌ Error: Please update the GITHUB_RAW_URL with your actual raw GitHub link.")
        return

    existing_files = get_sorted_art_files(".")
    total_found = len(existing_files)
    
    if total_found == 0:
        print("❌ Error: No 'art_X.jpg' files found locally to map to GitHub.")
        return

    limit = min(MAX_FILES, total_found)
    print(f"📸 Found {total_found} local art files. Verifying the first {limit} via GitHub URLs...")
    
    processed_count = 0
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for file_name in existing_files:
            if processed_count >= limit:
                break
                
            print(f"🔍 [{processed_count + 1}/{limit}] Processing {file_name} via GitHub link...")
            
            try:
                # Construct the direct, raw public URL for SerpApi
                public_url = f"{GITHUB_RAW_URL}{file_name}"
                
                # Pass that public URL to SerpApi
                response = requests.get(
                    "https://serpapi.com/search",
                    params={
                        "engine": "google_lens", 
                        "api_key": API_KEY,
                        "url": public_url
                    }
                )
                
                results = response.json()
                
                if "error" in results:
                    print(f"   ❌ SerpApi Error: {results['error']}")
                    out.write(f"{file_name} API_ERROR >>ERROR >>ERROR\n")
                    processed_count += 1
                    continue
                
                # Extract Google Lens metadata
                lens_matches = results.get("visual_matches", [])
                knowledge_graph = results.get("knowledge_graph", [])
                
                title = "Unknown Visual Title"
                author = "Unknown Visual Author"
                year = "Unknown Visual Year"
                
                if knowledge_graph:
                    kg = knowledge_graph[0]
                    title = kg.get("title", title)
                    author = kg.get("subtitle", author)
                elif lens_matches:
                    title = lens_matches[0].get("title", title)
                    if "source" in lens_matches[0]:
                        author = lens_matches[0].get("source", author)
                
                # Format output line
                output_line = f"{file_name} {title} >>{author} >>{year}\n"
                out.write(output_line)
                print(f"   👉 Detected: {title} by {author}")
                processed_count += 1
                
            except Exception as e:
                print(f"   ❌ Error searching {file_name}: {e}")
                out.write(f"{file_name} CRITICAL_ERROR >>ERROR >>ERROR\n")
                processed_count += 1

    print(f"\n✅ Visual verification log successfully saved to '{OUTPUT_FILE}'!")

if __name__ == "__main__":
    verify_images_visually()