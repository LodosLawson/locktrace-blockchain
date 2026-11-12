import os
import sys
import json
import urllib.request

sys.path.append('scripts')
from sync_to_notion import notion_api

HATALAR_PAGE_ID = "41234084-c76e-80cf-bbce-d681738e6165"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "scratch", "hatalar_images")
os.makedirs(OUT_DIR, exist_ok=True)

res = notion_api(f"blocks/{HATALAR_PAGE_ID}/children?page_size=100")
blocks = res.get("results", []) if res else []
print(f"Total blocks in Hatalar page: {len(blocks)}", flush=True)

img_idx = 0
items = []

for i, b in enumerate(blocks):
    btype = b.get("type")
    content_obj = b.get(btype, {})
    caption_list = content_obj.get("caption", [])
    text_list = content_obj.get("rich_text", [])
    caption = "".join(t.get("plain_text", "") for t in caption_list).strip()
    text = "".join(t.get("plain_text", "") for t in text_list).strip()
    
    img_url = None
    if btype == "image":
        img_url = content_obj.get("file", {}).get("url") or content_obj.get("external", {}).get("url")
    
    local_img_path = None
    if img_url:
        img_idx += 1
        local_img_path = os.path.join(OUT_DIR, f"image_{img_idx}.jpg")
        try:
            req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp, open(local_img_path, "wb") as f:
                f.write(resp.read())
            print(f"Downloaded Image #{img_idx}: {local_img_path}", flush=True)
        except Exception as e:
            print(f"Failed to download image {img_idx}: {e}", flush=True)
    
    items.append({
        "index": i,
        "type": btype,
        "text": text,
        "caption": caption,
        "image_file": local_img_path
    })

print("\n" + "="*80)
print("EXTRACTED NOTION HATALAR SUMMARY:")
print("="*80)
for it in items:
    if it["text"] or it["caption"] or it["image_file"]:
        print(f"\n--- Block #{it['index']} ({it['type']}) ---")
        if it["image_file"]:
            print(f"IMAGE: {it['image_file']}")
        if it["caption"]:
            print(f"CAPTION: {it['caption']}")
        if it["text"]:
            print(f"TEXT: {it['text']}")
print("="*80)

