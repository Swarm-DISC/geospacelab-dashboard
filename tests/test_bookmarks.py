"""Offline bookmark tests: integrity, apply, and save/load round-trip."""

import datetime as dt

import pytest

from gsl_dashboard import settings
from gsl_dashboard.bookmarks import all_bookmarks, apply_bookmark, load_seeds, save_user_bookmark
from gsl_dashboard.bookmarks import store
from gsl_dashboard.catalog import get_catalog
from gsl_dashboard.spec import RequestSpec, RunRequest
from gsl_dashboard.state import RequestState

CAT = get_catalog()


def test_seed_ids_unique():
    ids = [b.id for b in load_seeds()]
    assert len(ids) == len(set(ids))


def test_bookmark_datasets_resolve():
    for bm in all_bookmarks():
        assert bm.datasets
        for d in bm.datasets:
            product = CAT.get(d["dataset_id"])  # raises if unknown
            for key in d.get("params", {}):
                assert key in product.param_names, f"{bm.id}: bad param {key} for {product.id}"
            for v in d.get("variables", []):
                assert v in product.variables, f"{bm.id}: bad var {v}"


def test_apply_single_bookmark_sets_cascade():
    state = RequestState()
    bm = next(b for b in load_seeds() if b.id == "swarm_mag")
    apply_bookmark(bm, state)
    assert state.product == "swarm.mag_lr"
    assert state.category == "Swarm"
    assert state.datasets == []  # single-dataset -> editable
    assert "mag_lr" in state.code


def test_apply_multi_bookmark_populates_datasets():
    state = RequestState()
    bm = next(b for b in load_seeds() if b.id == "indices_storm")
    apply_bookmark(bm, state)
    assert len(state.datasets) == 3
    assert state.code.count("db.dock(") == 3


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "user_bookmarks.yaml"
    monkeypatch.setattr(settings, "USER_BOOKMARKS_PATH", target)
    monkeypatch.setattr(store.settings, "USER_BOOKMARKS_PATH", target)
    req = RunRequest(
        (RequestSpec("indices.dst", {}, ("Dst",)),),
        dt.datetime(2020, 1, 1),
        dt.datetime(2020, 1, 2),
    )
    saved = save_user_bookmark("My View", req, description="test")
    assert target.is_file()
    loaded = store.load_user()
    assert [b.id for b in loaded] == [saved.id]
    assert loaded[0].datasets[0]["dataset_id"] == "indices.dst"


def test_save_replaces_same_id(tmp_path, monkeypatch):
    target = tmp_path / "user_bookmarks.yaml"
    monkeypatch.setattr(settings, "USER_BOOKMARKS_PATH", target)
    monkeypatch.setattr(store.settings, "USER_BOOKMARKS_PATH", target)
    req = RunRequest((RequestSpec("indices.dst", {}, ("Dst",)),), dt.datetime(2020, 1, 1), dt.datetime(2020, 1, 2))
    save_user_bookmark("Dup", req)
    save_user_bookmark("Dup", req)
    assert len(store.load_user()) == 1
