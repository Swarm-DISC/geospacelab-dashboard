"""Out-of-process preview runner.

Invoked as a script: ``python preview_worker.py <request.pkl> <result.pkl>``. It reads a
pickled :class:`RunRequest`, renders the preview to a PNG (so the parent process never
holds a live matplotlib figure), and writes a pickled result dict to ``<result.pkl>``.

Running in its own process is what lets the dashboard *actually* stop a slow download: the
parent terminates this process and the in-flight network sockets die with it — something a
background thread inside the server process cannot do.
"""

from __future__ import annotations

import io
import pickle
import sys
from pathlib import Path

# Importable whether installed or run from the src/ layout (mirrors app.py's path shim).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _render(req) -> dict:
    from gsl_dashboard.bootstrap import seed_geospacelab_config

    seed_geospacelab_config()  # MUST run before geospacelab is imported

    from gsl_dashboard import settings
    from gsl_dashboard.catalog import get_catalog
    from gsl_dashboard.runner import build_and_render

    result = build_and_render(req, get_catalog())

    png = None
    if result.fig is not None:
        buf = io.BytesIO()
        result.fig.savefig(buf, format="png", dpi=settings.PREVIEW_DPI, bbox_inches="tight")
        png = buf.getvalue()
    return {"png": png, "data_repr": result.data_repr, "error": result.error, "log": result.log}


def main(in_path: str, out_path: str) -> None:
    with open(in_path, "rb") as f:
        req = pickle.load(f)
    out = _render(req)
    with open(out_path, "wb") as f:
        pickle.dump(out, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
