"""Bookmarks: presets that load a saved selection + view into the dashboard state."""

from __future__ import annotations

from ..spec import RequestSpec
from .store import Bookmark, all_bookmarks, load_seeds, load_user, save_user_bookmark

__all__ = [
    "Bookmark",
    "all_bookmarks",
    "load_seeds",
    "load_user",
    "save_user_bookmark",
    "apply_bookmark",
]


def apply_bookmark(bookmark: Bookmark, state) -> None:
    """Load a bookmark into the reactive state, regenerating code once at the end.

    Single-dataset bookmarks load into the editable widgets (``datasets`` stays empty);
    multi-dataset bookmarks populate the added-datasets list for a combined plot.
    """
    specs = [
        RequestSpec(d["dataset_id"], dict(d.get("params", {})), tuple(d.get("variables", [])))
        for d in bookmark.datasets
    ]
    if not specs:
        return
    first = specs[0]
    product = state.catalog.get(first.dataset_id)

    with state._suspended():
        # Drive the cascade explicitly (watchers fire, but code regen is suspended).
        state.category = product.category
        state.source_group = product.source
        state.product = first.dataset_id
        # Apply the bookmark's params over the descriptor defaults set by _on_product.
        for key, value in first.params.items():
            try:
                setattr(state, key, value)
            except Exception:
                pass
        if first.variables:
            state.variables = list(first.variables)
        if bookmark.dt_fr is not None:
            state.dt_fr = bookmark.dt_fr
        if bookmark.dt_to is not None:
            state.dt_to = bookmark.dt_to
        state.datasets = specs if len(specs) > 1 else []

    state._regen()
