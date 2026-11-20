"""Build dist/VAJA-AI-<date>.zip to install on another Windows machine.

Only listed project files go in (allowlist), so notes, keys, .env, data/ (jobs, models, logs,
UI settings), .venv and caches can never slip in. Every file is also scanned for things that
look like secrets (API keys, access tokens); the build stops if one is found.
On the target machine: extract the zip, double-click "Install VAJA AI.cmd".
"""
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIRS = ["app", "worker", "scripts", "installer", "tests", "docs", "integrations"]
INCLUDE_FILES = ["Install VAJA AI.cmd", "README.md", "Multi_Input_Thai_ASR_Blueprint.md", "requirements.txt",
                 "requirements.lock.txt", "requirements-gpu-windows.txt", ".env.example", ".env.gpu.example",
                 "Dockerfile", "compose.yaml", ".dockerignore", ".gitignore", "pytest.ini", "start.ps1"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", "build", "env"}  # integrations/*/env holds local .env.dev
SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".zip"}
SECRET_PATTERNS = {
    "GitLab token": r"glpat-[0-9A-Za-z_\-.]{20,}",
    "GitHub token": r"gh[pousr]_[0-9A-Za-z]{30,}",
    "Anthropic key": r"sk-ant-[0-9A-Za-z_\-]{20,}",
    "OpenAI-style key": r"\bsk-[0-9A-Za-z]{32,}",
    "AWS key": r"AKIA[0-9A-Z]{16}",
    "Private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "Filled secret in env": r"(?m)^(API_TOKEN|ANTHROPIC_API_KEY)=\S+",
}


def files():
    for name in INCLUDE_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for folder in INCLUDE_DIRS:
        for path in sorted((ROOT / folder).rglob("*")):
            rel = path.relative_to(ROOT)
            if path.is_file() and not SKIP_PARTS & set(rel.parts[:-1]) and path.suffix not in SKIP_SUFFIXES:
                yield path


def scan(paths):
    found = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if re.search(pattern, text):
                found.append(f"{path.relative_to(ROOT)}: {label}")
    return found


def main():
    paths = list(files())
    secrets = scan(paths)
    if secrets:
        sys.exit("Refusing to package; remove these secrets first:\n  " + "\n  ".join(secrets))
    out = ROOT / "dist" / f"VAJA-AI-{date.today():%Y%m%d}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            z.write(path, Path("VAJA AI") / path.relative_to(ROOT))
    print(f"{out} ({len(paths)} files, {out.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
