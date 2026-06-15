import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

# Always run with backend as cwd so imports and relative paths stay consistent
# regardless of where the process is launched from (frontend/, mvp/, repo root).
os.chdir(BACKEND_DIR)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import uvicorn
from server import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
