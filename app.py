"""Panel entrypoint: `panel serve app.py`.

Seeds geospacelab's config BEFORE the package is imported (geospacelab prompts on stdin
on first import with no config), then builds and serves the dashboard.
"""

import sys
from pathlib import Path

# Make the src/ layout importable without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from gsl_dashboard.bootstrap import seed_geospacelab_config  # noqa: E402

seed_geospacelab_config()

from gsl_dashboard.ui.layout import build_app  # noqa: E402

build_app().servable()
