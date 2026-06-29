"""Detect optional geospacelab capabilities (heavy/compiled coordinate packages).

Used to gate previews that would otherwise fail deep inside geospacelab with an opaque
"The data source cannot be docked" message.
"""

from __future__ import annotations

import functools
import importlib.util


@functools.lru_cache(maxsize=None)
def _importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def apex_available() -> bool:
    """apexpy — needed for ``add_APEX`` (APEX/QD magnetic coordinates)."""
    return _importable("apexpy")


def aacgm_available() -> bool:
    """aacgmv2 — needed for ``add_AACGM`` (AACGM magnetic coordinates)."""
    return _importable("aacgmv2")
