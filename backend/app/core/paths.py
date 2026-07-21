"""Filesystem paths derived from source location (not process CWD)."""

from pathlib import Path

# backend/app/core/paths.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

APP_ROOT = BACKEND_ROOT / "app"
DASHBOARD_DIR = BACKEND_ROOT / "dashboard"
ENV_FILE = BACKEND_ROOT / ".env"
