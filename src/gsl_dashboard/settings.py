"""Runtime configuration for the dashboard.

Two runtime modes, selected by ``DASHBOARD_MODE``:

* ``local`` (default) — run against the operator's already-configured geospacelab
  install. We never touch ``~/.geospacelab/config.toml``; whatever data path and
  credentials are configured there are used as-is.
* ``docker`` — a restricted runtime. We seed an ephemeral config pointing the data
  root at a temp directory, and the runner refuses live previews for any source whose
  credentials aren't configured (code is still generated). Passing credentials as env
  vars (e.g. ``VIRES_TOKEN``; see deploy/entrypoint.sh) re-enables that source's preview.
"""

from __future__ import annotations

import os
from pathlib import Path

# Load a local .env if present (no-op if python-dotenv is missing or the file is absent).
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


# --- Runtime mode -----------------------------------------------------------------
MODE = os.environ.get("DASHBOARD_MODE", "local").strip().lower()
if MODE not in ("local", "docker"):
    MODE = "local"


def is_docker() -> bool:
    """True when running in the restricted Docker runtime."""
    return MODE == "docker"


# Data root used only in docker mode. Empty -> bootstrap creates a temp directory.
DOCKER_DATA_ROOT = os.environ.get("GEOSPACELAB_DATA_ROOT", "").strip()

# --- Preview guardrails ------------------------------------------------------------
PREVIEW_TIMEOUT_SECONDS = int(os.environ.get("GSL_PREVIEW_TIMEOUT", "180"))
PREVIEW_DPI = int(os.environ.get("GSL_PREVIEW_DPI", "96"))

# Attempt live previews for geomap sources (AMPERE/SuperDARN). These need cartopy and a
# manually downloaded file, so previews are off by default even outside docker mode.
ENABLE_GEOMAP_PREVIEW = _flag("GSL_ENABLE_GEOMAP_PREVIEW", default=False)

# WDC (AE/ASY-SYM/Dst, also used by OMNI) asks for a contact email on first download.
# Injected into geospacelab's in-memory config so the server never blocks on stdin.
# Empty -> bootstrap falls back to the configured esa_eo username, then a placeholder.
WDC_USER_EMAIL = os.environ.get("GSL_WDC_EMAIL", "").strip()

# --- Project paths -----------------------------------------------------------------
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
USER_BOOKMARKS_PATH = DATA_DIR / "user_bookmarks.yaml"
