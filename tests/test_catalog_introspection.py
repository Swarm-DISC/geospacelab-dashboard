"""Drift detection: verify the catalog matches the installed geospacelab.

Marked ``install`` because it imports geospacelab. Run with ``pytest -m install``;
skipped automatically when geospacelab is not importable.
"""

import importlib

import pytest

from gsl_dashboard.catalog import get_catalog
from gsl_dashboard.catalog.models import DATAHUB, EXPRESS
from gsl_dashboard.catalog.registry import parse_target

pytestmark = pytest.mark.install

geospacelab = pytest.importorskip("geospacelab")
CAT = get_catalog()


def test_express_targets_importable():
    for p in CAT.products.values():
        if p.loader != EXPRESS:
            continue
        module_name, cls_name = parse_target(p.express_target)
        module = importlib.import_module(module_name)
        assert hasattr(module, cls_name), f"{p.id}: {p.express_target} missing"


def test_tsdashboard_api():
    from geospacelab.visualization.mpl.dashboards import TSDashboard

    for meth in ("dock", "set_layout", "draw", "show", "assign_variable", "add_title"):
        assert hasattr(TSDashboard, meth), meth


def test_figure_attribute_name():
    """The runner reads ``.figure``; pin it here so an upstream rename is caught."""
    import datetime as dt

    import matplotlib

    matplotlib.use("Agg")
    from geospacelab.visualization.mpl.dashboards import TSDashboard

    db = TSDashboard(dt_fr=dt.datetime(2015, 3, 17), dt_to=dt.datetime(2015, 3, 18), figure_config={"figsize": (4, 3)})
    fig = getattr(db, "figure", None)
    import matplotlib.figure

    assert isinstance(fig, matplotlib.figure.Figure)


def test_swarm_datasource_paths_exist():
    """Each SWARM datasource_contents should resolve to a real source package."""
    import pathlib

    root = pathlib.Path(geospacelab.__file__).parent / "datahub" / "sources"
    for p in CAT.products.values():
        if p.loader == DATAHUB and p.datasource_contents and p.datasource_contents[0] == "esa_eo":
            path = root.joinpath(*p.datasource_contents)
            assert path.is_dir(), f"{p.id}: {path} missing"
