import shutil
import hashlib
import json
import re

# 1. Sync frontend/index.html to templates/index.html
shutil.copyfile('frontend/index.html', 'templates/index.html')
print("Synced frontend/index.html -> templates/index.html")

# 2. Bump sw.js version to v48
for sw_path in ['frontend/sw.js', 'templates/sw.js']:
    with open(sw_path, 'r', encoding='utf-8') as f:
        sw_content = f.read()
    sw_content = re.sub(r'locktrace-pwa-v\d+', 'locktrace-pwa-v48', sw_content)
    with open(sw_path, 'w', encoding='utf-8') as f:
        f.write(sw_content)
    print(f"Updated {sw_path} to locktrace-pwa-v48")

# 3. Compute SHA256 of index.html and sw.js
with open('frontend/index.html', 'rb') as f:
    index_hash = hashlib.sha256(f.read()).hexdigest()
with open('frontend/sw.js', 'rb') as f:
    sw_hash = hashlib.sha256(f.read()).hexdigest()

integrity = {
    "version": "v48",
    "index_sha256": index_hash,
    "sw_sha256": sw_hash
}

for int_path in ['frontend/integrity.json', 'templates/integrity.json']:
    with open(int_path, 'w', encoding='utf-8') as f:
        json.dump(integrity, f, indent=2)
    print(f"Updated {int_path}")

print("Sync and integrity generation complete!")

