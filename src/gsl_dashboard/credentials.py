"""Report which geospacelab credentials are configured.

Reads the operator's ``~/.geospacelab/config.toml`` (and a couple of well-known token
locations). Used to gate live previews and drive the header status indicator. Credentials
themselves are owned by geospacelab — this module never writes them.
"""

from __future__ import annotations

import os
import pathlib

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

CONFIG_PATH = pathlib.Path.home() / ".geospacelab" / "config.toml"


def _config() -> dict:
    if tomllib is None or not CONFIG_PATH.is_file():
        return {}
    try:
        return tomllib.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def credentials_present(kind: str | None) -> bool:
    if kind is None:
        return True
    datahub = _config().get("datahub", {})
    if kind == "esa_eo":
        return bool(datahub.get("esa_eo", {}).get("username"))
    if kind == "madrigal":
        m = datahub.get("madrigal", {})
        return bool(m.get("user_fullname") and m.get("user_email"))
    if kind == "vires":
        if os.environ.get("VIRES_TOKEN"):
            return True
        return (pathlib.Path.home() / ".viresclient.ini").is_file()
    return True


def status() -> dict[str, bool]:
    """Map of credential kind -> configured?, for the header indicator."""
    return {kind: credentials_present(kind) for kind in ("esa_eo", "madrigal", "vires")}
