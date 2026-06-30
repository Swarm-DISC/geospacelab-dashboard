"""Prepare the process so geospacelab can be imported and run headlessly.

MUST be called (``seed_geospacelab_config()``) before anything imports geospacelab — the
first geospacelab import resolves its config and, with no config present, prompts on stdin.

* local mode — never touches ``~/.geospacelab/config.toml``; the operator's existing data
  path and credentials are used verbatim. Only sets a writable matplotlib cache and the
  Agg backend.
* docker mode — writes an ephemeral ``config.toml`` pointing ``data_root_dir`` at a temp
  directory (downloads are throwaway), creating the dir if needed.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

from . import settings

_CONFIG_PATH = pathlib.Path.home() / ".geospacelab" / "config.toml"


def _ensure_writable_mpl() -> None:
    """matplotlib needs a writable config/cache dir; default (~/.cache) may be read-only."""
    if not os.environ.get("MPLCONFIGDIR"):
        mpl_dir = pathlib.Path(tempfile.gettempdir()) / "gsl-mplconfig"
        mpl_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(mpl_dir)


def _use_agg() -> None:
    import matplotlib

    matplotlib.use("Agg")


def _seed_docker_config() -> str:
    import tomli_w

    data_root = settings.DOCKER_DATA_ROOT or tempfile.mkdtemp(prefix="gsl-data-")
    pathlib.Path(data_root).mkdir(parents=True, exist_ok=True)

    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Preserve any credentials an entrypoint already wrote; only set the data root.
    existing = {}
    if _CONFIG_PATH.is_file():
        try:
            import tomllib

            existing = tomllib.loads(_CONFIG_PATH.read_text())
        except Exception:
            existing = {}
    config = {**existing, "package_name": "geospacelab"}
    config.setdefault("datahub", {})
    config["datahub"]["data_root_dir"] = str(data_root)
    with open(_CONFIG_PATH, "wb") as f:
        tomli_w.dump(config, f)
    # Export so preview-worker subprocesses inherit the SAME data root (downloads stay
    # cached across previews instead of each worker minting a fresh temp dir).
    os.environ["GEOSPACELAB_DATA_ROOT"] = str(data_root)
    return data_root


def seed_geospacelab_config() -> None:
    _ensure_writable_mpl()
    _use_agg()
    if settings.is_docker():
        _seed_docker_config()
        return
    # local mode: use whatever the operator already configured. Only guard the stdin
    # prompt if there is genuinely no config (e.g. a fresh machine), so the server can't
    # hang waiting for input.
    if not _CONFIG_PATH.is_file():
        os.environ.setdefault("READTHEDOCS", "True")


_primed = False


def prime_in_memory_config() -> None:
    """Inject defaults that some sources would otherwise prompt for on stdin.

    Runs after geospacelab is importable (lazily, before the first dock). Writes only to
    geospacelab's in-memory ``pref.user_config`` — never to disk — so the operator's
    ``config.toml`` is left untouched in local mode.
    """
    global _primed
    if _primed:
        return
    _primed = True
    try:
        from geospacelab.config import pref
    except Exception:
        return
    uc = pref.user_config
    datahub = uc.setdefault("datahub", {})
    wdc = datahub.setdefault("wdc", {})
    if not wdc.get("user_email"):
        wdc["user_email"] = (
            settings.WDC_USER_EMAIL
            or datahub.get("esa_eo", {}).get("username")
            or "geospacelab@example.com"
        )
