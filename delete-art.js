const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Get the art ID/number from the terminal command
const targetId = process.argv[2];

if (!targetId) {
    console.error('\x1b[31m%s\x1b[0m', 'Error: Please provide an artwork ID number.');
    console.log('Example usage: node delete-art.js 2');
    process.exit(1);
}

const jsonPath = path.join(__dirname, 'feed.json');

// 1. Read and parse the current feed.json
fs.readFile(jsonPath, 'utf8', (err, data) => {
    if (err) {
        console.error('Error reading feed.json:', err);
        return;
    }

    let feed;
    try {
        feed = JSON.parse(data);
    } catch (parseErr) {
        console.error('Error parsing feed.json:', parseErr);
        return;
    }

    // 2. Match by parsing the filename out of the image_url field
    const itemIndex = feed.artwork_list.findIndex(item => {
        if (item && item.image_url) {
            // Extracts "art_2.jpg" from the URL
            const filename = path.basename(item.image_url).toLowerCase(); 
            const searchStr = String(targetId).trim().toLowerCase();

            // Matches if the filename is exactly what you typed, or contains "art_2"
            return filename === searchStr || 
                   filename.startsWith(searchStr + '.') || 
                   filename.startsWith('art_' + searchStr + '.');
        }
        return false;
    });

    if (itemIndex === -1) {
        console.error('\x1b[33m%s\x1b[0m', `Artwork matching "${targetId}" not found in feed.json URLs.`);
        return;
    }

    const itemToDelete = feed.artwork_list[itemIndex];
    let filename = path.basename(itemToDelete.image_url);
    let localImagePath = path.join(__dirname, 'images', filename);

    console.log(`\nFound artwork: "${itemToDelete.title || 'Untitled'}"`);

    // 3. Delete the physical image file locally
    if (fs.existsSync(localImagePath)) {
        try {
            fs.unlinkSync(localImagePath);
            console.log('\x1b[32m%s\x1b[0m', `✓ Successfully deleted physical file: images/${filename}`);
        } catch (fileErr) {
            console.error(`✕ Failed to delete image file: ${localImagePath}`, fileErr);
        }
    } else {
        console.log('\x1b[33m%s\x1b[0m', `! Note: Physical file images/${filename} was not found locally (already missing).`);
    }

    // 4. Remove the item from the JSON array
    feed.artwork_list.splice(itemIndex, 1);

    // 5. Save the updated feed.json back to your disk
    fs.writeFile(jsonPath, JSON.stringify(feed, null, 4), 'utf8', (writeErr) => {
        if (writeErr) {
            console.error('✕ Failed to update feed.json:', writeErr);
            return;
        }
        console.log('\x1b[32m%s\x1b[0m', `✓ Successfully removed from feed.json.`);

        // 6. Automatically sync changes to GitHub
        console.log('\n\x1b[36m%s\x1b[0m', 'Syncing changes with GitHub...');
        try {
            // Stage all changes and deletions
            execSync('git add -A', { stdio: 'ignore' });
            
            // Commit changes
            execSync(`git commit -m "Purge art_${targetId} from catalog and images"`, { stdio: 'ignore' });
            
            // Push to GitHub repository
            execSync('git push', { stdio: 'ignore' });
            
            console.log('\x1b[32m%s\x1b[0m', `🚀 GitHub updated! The image and JSON edits are live on your repository.`);
        } catch (gitError) {
            console.error('\x1b[31m%s\x1b[0m', '⚠ GitHub Sync failed. Run git push manually if needed.');
        }
    });
});