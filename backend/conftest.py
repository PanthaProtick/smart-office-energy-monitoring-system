import sys
from pathlib import Path

# Ensure `backend/` (this file's directory) is on sys.path so `import app...`
# works no matter which directory `pytest` is invoked from.
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
