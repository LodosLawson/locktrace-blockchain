# -*- coding: utf-8 -*-
"""
Converts raw white-background pixel-art avatar JPGs into crisp 512x512 transparent PNGs
using border-seeded flood-fill so internal white details (eyes, stripes, 'B' badge) stay intact.
"""
import os
from collections import deque
from PIL import Image

SRC_DIR = r"C:\Users\mehem\Downloads\Animal"
DST_DIRS = [
    os.path.join("frontend", "avatars", "animals"),
    os.path.join("templates", "avatars", "animals"),
]

MAPPING = {
    "ahtapot.jpg": "octopus.png",
    "ari.jpg": "bee.png",
    "flamingo.jpg": "flamingo.png",
    "gelincik.jpg": "weasel.png",
    "kaplunbaga.jpg": "turtle.png",
    "karinca.jpg": "ant.png",
    "kartal.jpg": "eagle.png",
    "ornitorneg.jpg": "platypus.png",
    "rakun.jpg": "raccoon.png",
    "shark.jpg": "shark.png",
    "yilan.jpg": "snake.png",
    "zebra.jpg": "zebra.png",
    "zurafa.jpg": "giraffe.png",
}


def remove_white_bg_floodfill(img: Image.Image, threshold: int = 232) -> Image.Image:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    pixels = rgba.load()

    visited = bytearray(w * h)
    q = deque()

    def is_bg(r: int, g: int, b: int) -> bool:
        return r >= threshold and g >= threshold and b >= threshold and (max(r, g, b) - min(r, g, b)) <= 22

    # Seed from all 4 borders
    for x in range(w):
        for y in (0, h - 1):
            r, g, b, _ = pixels[x, y]
            if is_bg(r, g, b):
                idx = y * w + x
                if not visited[idx]:
                    visited[idx] = 1
                    q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            r, g, b, _ = pixels[x, y]
            if is_bg(r, g, b):
                idx = y * w + x
                if not visited[idx]:
                    visited[idx] = 1
                    q.append((x, y))

    while q:
        cx, cy = q.popleft()
        pixels[cx, cy] = (255, 255, 255, 0)
        if cx > 0:
            idx = cy * w + (cx - 1)
            if not visited[idx]:
                r, g, b, _ = pixels[cx - 1, cy]
                if is_bg(r, g, b):
                    visited[idx] = 1
                    q.append((cx - 1, cy))
        if cx + 1 < w:
            idx = cy * w + (cx + 1)
            if not visited[idx]:
                r, g, b, _ = pixels[cx + 1, cy]
                if is_bg(r, g, b):
                    visited[idx] = 1
                    q.append((cx + 1, cy))
        if cy > 0:
            idx = (cy - 1) * w + cx
            if not visited[idx]:
                r, g, b, _ = pixels[cx, cy - 1]
                if is_bg(r, g, b):
                    visited[idx] = 1
                    q.append((cx, cy - 1))
        if cy + 1 < h:
            idx = (cy + 1) * w + cx
            if not visited[idx]:
                r, g, b, _ = pixels[cx, cy + 1]
                if is_bg(r, g, b):
                    visited[idx] = 1
                    q.append((cx, cy + 1))

    # Clean 1px JPG halo fringe adjacent to transparent pixels
    halo_coords = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            r, g, b, a = pixels[x, y]
            if a > 0 and r >= 205 and g >= 205 and b >= 205 and (max(r, g, b) - min(r, g, b)) <= 24:
                if (
                    pixels[x - 1, y][3] == 0
                    or pixels[x + 1, y][3] == 0
                    or pixels[x, y - 1][3] == 0
                    or pixels[x, y + 1][3] == 0
                ):
                    halo_coords.append((x, y))
    for x, y in halo_coords:
        pixels[x, y] = (255, 255, 255, 0)

    return rgba


def main():
    for d in DST_DIRS:
        os.makedirs(d, exist_ok=True)

    for src_name, dst_name in MAPPING.items():
        src_path = os.path.join(SRC_DIR, src_name)
        if not os.path.exists(src_path):
            print(f"[WARN] Missing {src_path}")
            continue
        with Image.open(src_path) as im:
            # Downscale first to 512x512 for fast, clean flood-fill & crisp pixel edges
            im_small = im.resize((512, 512), Image.Resampling.LANCZOS)
            out = remove_white_bg_floodfill(im_small, threshold=232)
            # Crop to content bounding box + add balanced 10% padding so all avatars are framed nicely
            bbox = out.getbbox()
            if bbox:
                cropped = out.crop(bbox)
                cw, ch = cropped.size
                side = int(max(cw, ch) * 1.18)
                canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                canvas.paste(cropped, ((side - cw) // 2, (side - ch) // 2), cropped)
                final_img = canvas.resize((512, 512), Image.Resampling.LANCZOS)
            else:
                final_img = out

            for d in DST_DIRS:
                dst_path = os.path.join(d, dst_name)
                final_img.save(dst_path, format="PNG", optimize=True)
            kb = os.path.getsize(os.path.join(DST_DIRS[0], dst_name)) / 1024.0
            print(f"[OK] {src_name:16s} -> {dst_name:14s} ({kb:.1f} KB)")


if __name__ == "__main__":
    main()
