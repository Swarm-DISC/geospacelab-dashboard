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
import sys
import tempfile
import types

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


def _neutralize_turtle_import() -> None:
    """Stop geospacelab's Swarm downloaders from dragging in Tkinter.

    Every ``esa_eo/swarm/*/downloader.py`` carries a stray ``from turtle import rt`` (an
    IDE autocomplete slip — ``rt`` is never used). Importing ``turtle`` pulls in
    ``tkinter`` -> ``_tkinter`` -> ``libtk8.6.so``, which isn't present in a headless slim
    image, so docking *any* Swarm product dies with "libtk8.6.so: cannot open shared
    object file" — even for the token-free HAPI backend that needs no GUI at all. Each
    dataset imports its ``downloader`` at module load, so this fires regardless of the
    chosen source. Pre-seed a stub ``turtle`` (exposing the ``rt`` name the import binds)
    so the dead import resolves without loading Tk. ``setdefault`` leaves a real ``turtle``
    alone if something legitimately imported it first.
    """
    if "turtle" not in sys.modules:
        stub = types.ModuleType("turtle")
        stub.rt = None  # the only name those downloaders bind; never called
        sys.modules["turtle"] = stub


def _neutralize_keyring() -> None:
    """Point keyring at the no-op backend so it never prompts or raises in a container.

    geospacelab's credentialed sources (esa_eo/swarm, madrigal, …) call
    ``keyring.get_password`` at *import time*. In a minimal image (python:3.12-slim, no
    D-Bus/Secret Service) keyring resolves to the ``fail`` backend, whose ``get_password``
    raises ``NoKeyringError`` — which would abort the import even when we never use the
    stored password (HAPI/VirES Swarm need none). The null backend returns ``None``
    instead; combined with ``_on_rtd`` (see :func:`prime_in_memory_config`), the import
    completes without touching stdin. ``setdefault`` so an operator's choice still wins.
    """
    os.environ.setdefault("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")


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
    _neutralize_turtle_import()  # mode-independent: Swarm imports break without Tk otherwise
    if settings.is_docker():
        _neutralize_keyring()
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

    # Headless docker: make geospacelab's credentialed sources stop prompting on stdin.
    # Their ``__init__`` modules gate every interactive fallback (username/password input,
    # "create data dir?", …) behind ``pref._on_rtd``; flipping it here — *after* ``pref``
    # is built, so the docker data root resolved in _seed_docker_config() is untouched —
    # lets a Swarm dataset import cleanly for the token-free (HAPI) and token (VirES)
    # backends instead of dying on the ESA EO prompt. Local mode keeps the operator's real
    # credentials, so we never force this there.
    if settings.is_docker():
        pref._on_rtd = True

    uc = pref.user_config
    datahub = uc.setdefault("datahub", {})
    wdc = datahub.setdefault("wdc", {})
    if not wdc.get("user_email"):
        wdc["user_email"] = (
            settings.WDC_USER_EMAIL
            or datahub.get("esa_eo", {}).get("username")
            or "geospacelab@example.com"
        )
