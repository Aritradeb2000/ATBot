"""
ATBot — Vercel Service Entrypoint
Mounts the FastAPI app with sys.path configuration for Vercel multi-service deployment.
"""
import sys
from pathlib import Path

# Add project root and backend dir to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from backend.api.main import app

__all__ = ["app"]

