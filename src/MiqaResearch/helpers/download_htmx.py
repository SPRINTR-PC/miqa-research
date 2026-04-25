import os
import requests
from pathlib import Path

# Configuration
# Fetch latest version or use latest stable version known.
# For htmx.org, we can check their latest release on GitHub or similar, but
# using "latest" with unpkg works well.
HTMX_VERSION = "latest"
BASE_URL = f"https://unpkg.com/htmx.org@{HTMX_VERSION}/dist/"
EXTENSIONS_URL = f"https://unpkg.com/htmx.org@{HTMX_VERSION}/dist/ext/"

# Target directory: MiqaResearch/static/js/htmx
BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = BASE_DIR / "static" / "js" / "htmx"

# List of common extensions to download
EXTENSIONS = [
    "ajax-header.js",
    "event-header.js",
    "head-support.js",
    "json-enc.js",
    "method-override.js",
    "morphdom-swap.js",
    "multi-swap.js",
    "path-deps.js",
    "preload.js",
    "remove-me.js",
    "response-targets.js",
    "restored.js",
    "sse.js",
    "ws.js",
]

def download_file(url, target_path):
    print(f"Downloading {url} to {target_path}...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        target_path.write_bytes(response.content)
        print(f"Successfully downloaded {target_path.name}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {url}: {e}")

def main():
    # Create target directory if it doesn't exist
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download main htmx file
    download_file(f"{BASE_URL}htmx.min.js", TARGET_DIR / "htmx.min.js")
    
    # Create extensions directory within htmx directory
    ext_dir = TARGET_DIR / "ext"
    ext_dir.mkdir(exist_ok=True)

    # Download extensions
    for ext in EXTENSIONS:
        download_file(f"{EXTENSIONS_URL}{ext}", ext_dir / ext)

if __name__ == "__main__":
    main()
