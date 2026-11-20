"""Build the VAJA Transcript Analyst app package (zip) for upload to Microsoft 365.

Resolves ${{VAR}} from env/.env.dev and $[file('...')] in declarativeAgent.json, validates
JSON and limits, generates icons if missing, and writes build/vaja-transcript-analyst.zip.
Usage: python integrations/m365-copilot/build_package.py [--env env/.env.dev] [--allow-placeholders]
"""
import argparse
import json
import re
import struct
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "appPackage"
FILES = ["manifest.json", "declarativeAgent.json", "ai-plugin.json", "apiSpecificationFile/vaja-openapi.yaml",
         "color.png", "outline.png"]
PLACEHOLDER = re.compile(r"\$\{\{([A-Z0-9_]+)\}\}")


def png(size, pixel):
    """Minimal RGBA PNG writer (stdlib only)."""
    rows = b"".join(b"\0" + b"".join(bytes(pixel(x, y, size)) for x in range(size)) for y in range(size))
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def on_v(x, y, size, stroke):
    """True when (x, y) lies on a 'V' glyph spanning the middle of the icon."""
    top, bottom = size * 0.25, size * 0.75
    if not top <= y <= bottom:
        return False
    t = (y - top) / (bottom - top)
    left, right = size * (0.25 + 0.25 * t), size * (0.75 - 0.25 * t)
    return abs(x - left) <= stroke or abs(x - right) <= stroke


def ensure_icons():
    color, outline = PACKAGE / "color.png", PACKAGE / "outline.png"
    if not color.exists():  # 192x192 full-color icon: white V on accent background
        color.write_bytes(png(192, lambda x, y, s: (255, 255, 255, 255) if on_v(x, y, s, 9) else (31, 95, 91, 255)))
    if not outline.exists():  # 32x32 outline icon: white on transparent
        outline.write_bytes(png(32, lambda x, y, s: (255, 255, 255, 255) if on_v(x, y, s, 1.6) else (0, 0, 0, 0)))


def load_env(path):
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def resolve(text, env, allow_placeholders, name):
    missing = sorted({k for k in PLACEHOLDER.findall(text) if not env.get(k)})
    if missing and not allow_placeholders:
        sys.exit(f"{name}: set {', '.join(missing)} in the env file")
    return PLACEHOLDER.sub(lambda m: env.get(m.group(1)) or m.group(0), text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=ROOT / "env" / ".env.dev")
    parser.add_argument("--allow-placeholders", action="store_true", help="validate structure only")
    args = parser.parse_args()
    env = load_env(args.env) if args.env.exists() else {}
    if not env and not args.allow_placeholders:
        sys.exit(f"Missing {args.env}; copy env/.env.dev.example and fill it in")
    ensure_icons()
    out = {}
    for name in FILES:
        path = PACKAGE / name
        if name.endswith(".png"):
            out[name] = path.read_bytes()
            continue
        text = resolve(path.read_text(encoding="utf-8"), env, args.allow_placeholders, name)
        if name == "declarativeAgent.json":
            text = re.sub(r"\$\[file\('([^']+)'\)\]",
                          lambda m: json.dumps((PACKAGE / m.group(1)).read_text(encoding="utf-8").strip())[1:-1], text)
            agent = json.loads(text)
            assert len(agent["instructions"]) <= 8000, f"instructions {len(agent['instructions'])} > 8000 chars"
            assert len(agent["name"]) <= 100 and len(agent["description"]) <= 1000
            assert len(agent.get("conversation_starters", [])) <= 12
            assert len(agent["disclaimer"]["text"]) <= 500
        elif name.endswith(".json"):
            json.loads(text)
        out[name] = text.encode("utf-8")
    manifest = json.loads(out["manifest.json"])
    assert len(manifest["name"]["short"]) <= 30 and len(manifest["description"]["short"]) <= 80
    plugin = json.loads(out["ai-plugin.json"])
    spec = out["apiSpecificationFile/vaja-openapi.yaml"].decode("utf-8")
    for function in plugin["functions"]:
        assert f"operationId: {function['name']}" in spec, f"no operationId {function['name']}"
    target = ROOT / "build" / "vaja-transcript-analyst.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in out.items():
            archive.writestr(name, data)
    print(f"Package: {target} ({len(out)} files, instructions {len(agent['instructions'])} chars)")


if __name__ == "__main__":
    main()
