"""Load shipped + user bookmarks and persist user-saved ones."""

from __future__ import annotations

import datetime as dt
import pathlib
import re
from dataclasses import dataclass, field

import yaml

from .. import settings

_SEEDS_PATH = pathlib.Path(__file__).resolve().parent / "seeds.yaml"


@dataclass
class Bookmark:
    id: str
    name: str
    description: str = ""
    dt_fr: dt.datetime | None = None
    dt_to: dt.datetime | None = None
    datasets: list[dict] = field(default_factory=list)
    builtin: bool = True


def _coerce_dt(value) -> dt.datetime | None:
    if value is None or isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    return dt.datetime.fromisoformat(str(value))


def _from_dict(d: dict, builtin: bool) -> Bookmark:
    return Bookmark(
        id=d["id"],
        name=d["name"],
        description=d.get("description", ""),
        dt_fr=_coerce_dt(d.get("dt_fr")),
        dt_to=_coerce_dt(d.get("dt_to")),
        datasets=list(d.get("datasets", [])),
        builtin=builtin,
    )


def _load_file(path: pathlib.Path, builtin: bool) -> list[Bookmark]:
    if not path.is_file():
        return []
    docs = yaml.safe_load(path.read_text()) or []
    return [_from_dict(d, builtin) for d in docs]


def load_seeds() -> list[Bookmark]:
    return _load_file(_SEEDS_PATH, builtin=True)


def load_user() -> list[Bookmark]:
    return _load_file(settings.USER_BOOKMARKS_PATH, builtin=False)


def all_bookmarks() -> list[Bookmark]:
    return load_seeds() + load_user()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "bookmark"


def save_user_bookmark(name: str, request, description: str = "") -> Bookmark:
    """Persist the current request as a user bookmark; returns the saved Bookmark."""
    bm = {
        "id": _slugify(name),
        "name": name,
        "description": description,
        "dt_fr": request.dt_fr.isoformat(),
        "dt_to": request.dt_to.isoformat(),
        "datasets": [
            {"dataset_id": s.dataset_id, "params": dict(s.params), "variables": list(s.variables)}
            for s in request.datasets
        ],
    }
    path = settings.USER_BOOKMARKS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = yaml.safe_load(path.read_text()) if path.is_file() else None
    existing = existing or []
    existing = [b for b in existing if b.get("id") != bm["id"]]  # replace same id
    existing.append(bm)
    path.write_text(yaml.safe_dump(existing, sort_keys=False, allow_unicode=True))
    return _from_dict(bm, builtin=False)
