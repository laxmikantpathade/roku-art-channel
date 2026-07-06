import os
import sys
import json
import subprocess

def main():
    if len(sys.argv) < 2:
        print("\033[91mError: Please provide an artwork ID number.\033[0m")
        print("Example usage: python3 delete_art.py 2")
        sys.exit(1)

    target_id = str(sys.argv[1]).strip().lower()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, 'feed.json')

    changes_made = False

    # --- Phase 1: Hunt and Destroy the Physical File ---
    print(f"\n\033[96mPhase 1: Searching for physical image files matching '{target_id}'...\033[0m")
    
    # We check both the main folder AND an 'images' folder just in case
    search_dirs = [base_dir, os.path.join(base_dir, 'images')]
    
    for d in search_dirs:
        if not os.path.exists(d):
            continue
        for filename in os.listdir(d):
            lower_file = filename.lower()
            # Check if it's an image and matches our target ID pattern
            if lower_file.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                if lower_file == target_id or \
                   lower_file.startswith(f"{target_id}.") or \
                   lower_file.startswith(f"image_{target_id}."):
                    
                    file_path = os.path.join(d, filename)
                    try:
                        os.remove(file_path)
                        print(f"\033[92m✓ Deleted orphaned file: {os.path.relpath(file_path, base_dir)}\033[0m")
                        changes_made = True
                    except Exception as e:
                        print(f"\033[91m✕ Failed to delete {file_path}. Error: {e}\033[0m")

    # --- Phase 2: Clean the JSON File ---
    print(f"\n\033[96mPhase 2: Checking feed.json for references...\033[0m")
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                feed = json.load(f)
            
            artwork_list = feed.get('artwork_list', [])
            item_index = -1

            for idx, item in enumerate(artwork_list):
                image_url = item.get('image_url', '')
                if image_url:
                    filename = os.path.basename(image_url).lower()
                    if filename == target_id or \
                       filename.startswith(f"{target_id}.") or \
                       filename.startswith(f"image_{target_id}."):
                        item_index = idx
                        break

            if item_index != -1:
                item_to_delete = artwork_list[item_index]
                print(f"\033[92m✓ Found in JSON: \"{item_to_delete.get('title', 'Untitled')}\"\033[0m")
                artwork_list.pop(item_index)
                feed['artwork_list'] = artwork_list

                # Save the updated JSON
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(feed, f, indent=4, ensure_ascii=False)
                print(f"\033[92m✓ Successfully removed reference from feed.json.\033[0m")
                changes_made = True
            else:
                print(f"\033[93m! No reference found in feed.json (Already clean).\033[0m")

        except Exception as e:
            print(f"\033[91m✕ Error parsing feed.json: {e}\033[0m")
    else:
        print(f"\033[91m! feed.json not found at {json_path}\033[0m")

    # --- Phase 3: Sync to GitHub ---
    if changes_made:
        print("\n\033[96mPhase 3: Syncing changes with GitHub...\033[0m")
        try:
            subprocess.run(["git", "add", "-A"], check=True)
            commit_message = f"Purge image_{target_id} from catalog and images"
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            subprocess.run(["git", "push"], check=True)
            print(f"\033[92m🚀 GitHub updated! The clean sweep is complete.\033[0m")
        except subprocess.CalledProcessError:
            print(f"\n\033[91m⚠ GitHub Sync failed! Check the Git output above.\033[0m")
    else:
        print("\n\033[93mNo changes needed to be made (File and JSON were already clean). GitHub sync skipped.\033[0m")

if __name__ == '__main__':
    main()