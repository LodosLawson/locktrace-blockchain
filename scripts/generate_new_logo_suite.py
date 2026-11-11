#!/usr/bin/env python3
"""
LockTrace Official Logo & PWA Icon Suite Generator
Generates pixel-perfect icons from the official brand logo.
"""
import os
import base64
import io
import shutil
from PIL import Image

DEFAULT_UPLOADED_PATH = os.path.join(
    os.path.expanduser("~"),
    ".gemini", "antigravity", "brain", "e94df9ad-452a-40fd-9546-259750b5d3e6",
    ".user_uploaded", "media_1794434951348_506db067.jpg"
)
UPLOADED_PATH = os.environ.get("LOCKTRACE_LOGO_SOURCE", DEFAULT_UPLOADED_PATH)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_ICONS_DIR = os.path.join(ROOT_DIR, "frontend", "icons")
TEMPLATES_ICONS_DIR = os.path.join(ROOT_DIR, "templates", "icons")
FRONTEND_FAVICON = os.path.join(ROOT_DIR, "frontend", "favicon.ico")
TEMPLATES_FAVICON = os.path.join(ROOT_DIR, "templates", "favicon.ico")

def generate_logo_suite():
    os.makedirs(FRONTEND_ICONS_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_ICONS_DIR, exist_ok=True)

    source_path = UPLOADED_PATH if os.path.exists(UPLOADED_PATH) else os.path.join(FRONTEND_ICONS_DIR, "icon-512.png")
    img = Image.open(source_path).convert('RGB')
    w, h = img.size
    pixels = img.load()

    # 1. Clean near-white background noise (compression artifacts) to pure white #ffffff
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            if (r + g + b) / 3 >= 244:
                pixels[x, y] = (255, 255, 255)

    # 2. Symmetrical square crop around optical center (527, 520) with size 600x600 if raw upload
    if w >= 600 and h >= 600:
        center_x = min(w // 2, 527)
        center_y = min(h // 2, 520)
        crop_size = min(w, h, 600)
        left = max(0, center_x - crop_size // 2)
        top = max(0, center_y - crop_size // 2)
        right = left + crop_size
        bottom = top + crop_size
        master_square = img.crop((left, top, right, bottom))
    else:
        master_square = img

    # 3. Generate PNG sizes
    sizes = {
        "icon-512.png": (512, 512),
        "icon-192.png": (192, 192),
        "icon-32.png": (32, 32),
        "icon-maskable-512.png": (512, 512),
        "icon-maskable-192.png": (192, 192),
        "apple-touch-icon.png": (180, 180),
    }

    generated_images = {}
    for filename, (dim_w, dim_h) in sizes.items():
        resized = master_square.resize((dim_w, dim_h), Image.Resampling.LANCZOS)
        out_path = os.path.join(FRONTEND_ICONS_DIR, filename)
        resized.save(out_path, format="PNG", optimize=True)
        # Sync to templates/icons
        shutil.copy2(out_path, os.path.join(TEMPLATES_ICONS_DIR, filename))
        generated_images[filename] = resized
        print(f"✅ Generated: {filename} ({dim_w}x{dim_h})")

    # 4. Generate multi-resolution Favicon (.ico: 16x16, 32x32, 48x48)
    ico_32 = master_square.resize((32, 32), Image.Resampling.LANCZOS)

    ico_32.save(
        FRONTEND_FAVICON,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)]
    )
    shutil.copy2(FRONTEND_FAVICON, TEMPLATES_FAVICON)
    print("✅ Generated: frontend/favicon.ico & templates/favicon.ico")

    # 5. Generate high-definition SVG icons with embedded base64 PNG
    buf = io.BytesIO()
    generated_images["icon-512.png"].save(buf, format="PNG", optimize=True)
    b64_512 = base64.b64encode(buf.getvalue()).decode("ascii")

    svg_content_512 = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="#ffffff"/>
  <image width="512" height="512" href="data:image/png;base64,{b64_512}"/>
</svg>
'''
    svg_path_512 = os.path.join(FRONTEND_ICONS_DIR, "icon.svg")
    with open(svg_path_512, "w", encoding="utf-8") as f:
        f.write(svg_content_512)
    shutil.copy2(svg_path_512, os.path.join(TEMPLATES_ICONS_DIR, "icon.svg"))
    print("✅ Generated: icon.svg")

    # AUD-05: Embed lightweight 32x32 base64 PNG into icon-32.svg instead of 512x512
    buf_32 = io.BytesIO()
    generated_images["icon-32.png"].save(buf_32, format="PNG", optimize=True)
    b64_32 = base64.b64encode(buf_32.getvalue()).decode("ascii")

    svg_content_32 = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="32" height="32" viewBox="0 0 32 32">
  <rect width="32" height="32" fill="#ffffff"/>
  <image width="32" height="32" href="data:image/png;base64,{b64_32}"/>
</svg>
'''
    svg_path_32 = os.path.join(FRONTEND_ICONS_DIR, "icon-32.svg")
    with open(svg_path_32, "w", encoding="utf-8") as f:
        f.write(svg_content_32)
    shutil.copy2(svg_path_32, os.path.join(TEMPLATES_ICONS_DIR, "icon-32.svg"))
    print("✅ Generated: icon-32.svg (optimized ~1KB)")

    print("\n🎉 ALL ICONS AND LOGOS GENERATED & SYNCHRONIZED SUCCESSFULLY!")

if __name__ == "__main__":
    generate_logo_suite()

