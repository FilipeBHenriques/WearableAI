from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
MVP_DIR = BACKEND_DIR.parent
DIST_DIR = (MVP_DIR / "frontend" / "dist").resolve()
ASSETS_DIR = DIST_DIR / "assets"
DB_PATH = (MVP_DIR / "data.db").resolve()
