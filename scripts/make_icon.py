"""Generate app/static/vaja.ico (desktop shortcut + browser favicon) and a PNG preview.

Pure numpy + zlib (no image library): each size is drawn directly with anti-aliased signed
distance fields, so 16 px stays crisp instead of being a blurry downscale.
Run: python -m scripts.make_icon
"""
import struct
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "vaja.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)

TOP_LEFT = np.array([124, 58, 237]) / 255      # violet
BOTTOM_RIGHT = np.array([236, 72, 153]) / 255  # pink
BAR_COLORS = ["#FFD23F", "#B5EF42", "#4FE3C1", "#B5EF42", "#FFD23F"]  # yellow, lime, aqua


def hex_rgb(value):
    return np.array([int(value[i:i + 2], 16) for i in (1, 3, 5)]) / 255


def rounded_box(px, py, cx, cy, hw, hh, r):
    """Signed distance to a rounded rectangle (negative inside)."""
    qx, qy = np.abs(px - cx) - hw + r, np.abs(py - cy) - hh + r
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    return outside + np.minimum(np.maximum(qx, qy), 0) - r


def coverage(dist, size):
    return np.clip(0.5 - dist * size, 0, 1)  # one pixel of anti-aliasing


def over(dst_rgb, dst_a, rgb, a):
    out_a = a + dst_a * (1 - a)
    safe = np.where(out_a > 0, out_a, 1)
    out_rgb = (rgb * a[..., None] + dst_rgb * (dst_a * (1 - a))[..., None]) / safe[..., None]
    return out_rgb, out_a


def render(size):
    c = (np.arange(size) + 0.5) / size
    px, py = np.meshgrid(c, c)
    rgb, alpha = np.zeros((size, size, 3)), np.zeros((size, size))

    # Background tile: diagonal violet -> pink gradient with a soft top highlight.
    margin = 0.02 if size >= 32 else 0.0
    tile = coverage(rounded_box(px, py, 0.5, 0.5, 0.5 - margin, 0.5 - margin, 0.22), size)
    t = np.clip((px + py) / 2, 0, 1)[..., None]
    grad = TOP_LEFT * (1 - t) + BOTTOM_RIGHT * t
    highlight = np.clip(0.55 - py, 0, 0.55)[..., None] * 0.35
    rgb, alpha = over(rgb, alpha, np.clip(grad + highlight, 0, 1), tile)

    # Sound-wave bars; three thicker bars at tiny sizes so they stay readable.
    if size <= 24:
        heights, colors, width, gap = [0.42, 0.66, 0.42], ["#FFD23F", "#B5EF42", "#4FE3C1"], 0.15, 0.08
    else:
        heights, colors, width, gap = [0.30, 0.52, 0.66, 0.52, 0.30], BAR_COLORS, 0.095, 0.05
    total = len(heights) * width + (len(heights) - 1) * gap
    x = 0.5 - total / 2 + width / 2
    for h, color in zip(heights, colors):
        if size >= 48:  # subtle drop shadow for depth
            shadow = coverage(rounded_box(px, py, x + 0.008, 0.52 + 0.012, width / 2, h / 2, width / 2), size) * 0.25
            rgb, alpha = over(rgb, alpha, np.zeros(3), shadow * tile)
        bar = coverage(rounded_box(px, py, x, 0.52, width / 2, h / 2, width / 2), size)
        rgb, alpha = over(rgb, alpha, hex_rgb(color), bar * tile)
        x += width + gap

    # Small white speech-bubble dot (top-right): "talk to text".
    if size >= 32:
        dot = coverage(np.hypot(px - 0.78, py - 0.22) - 0.075, size)
        rgb, alpha = over(rgb, alpha, np.ones(3), dot * 0.95)

    pixels = np.dstack([rgb, alpha[..., None]])
    return (np.clip(pixels, 0, 1) * 255 + 0.5).astype(np.uint8)


def png(image):
    h, w, _ = image.shape
    raw = b"".join(b"\x00" + image[y].tobytes() for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(images):
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs


def main(preview_dir=None):
    images = [(s, png(render(s))) for s in SIZES]
    OUT.write_bytes(ico(images))
    print(f"{OUT} ({OUT.stat().st_size // 1024} KB, sizes {', '.join(map(str, SIZES))})")
    if preview_dir:
        for s, data in images:
            (Path(preview_dir) / f"icon-{s}.png").write_bytes(data)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
