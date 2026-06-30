"""Offline codegen tests: structure, validity, and SWARM source/variant mapping."""

import ast
import datetime as dt

import pytest

from gsl_dashboard.catalog import get_catalog
from gsl_dashboard.codegen import build_dock_kwargs, figsize_for_panels, panel_count, render_code
from gsl_dashboard.spec import RequestSpec, RunRequest

CAT = get_catalog()
FR = dt.datetime(2015, 3, 17, 0, 0)
TO = dt.datetime(2015, 3, 18, 0, 0)


def _req(*specs):
    return RunRequest(tuple(specs), FR, TO)


def test_omni_express_snippet():
    code = render_code(_req(RequestSpec("omni.combined", {"omni_type": "OMNI2", "omni_res": "1min"})), CAT)
    ast.parse(code)
    assert "from geospacelab.express.omni_dashboard import OMNIDashboard" in code
    assert "OMNIDashboard(" in code
    assert "omni_type='OMNI2'" in code and "omni_res='1min'" in code
    assert ".quicklook()" in code


def test_indices_datahub_snippet():
    code = render_code(_req(RequestSpec("indices.kpap")), CAT)
    ast.parse(code)
    assert "TSDashboard(" in code
    assert "datasource_contents=['gfz', 'kpap']" in code
    assert "load_mode='AUTO'" in code and "allow_load=True" in code
    assert "db.set_layout(panel_layouts=panel_layouts)" in code


def test_swarm_source_variant_mapping():
    spec = RequestSpec(
        "swarm.mag_lr",
        {"sat_id": "A", "source": "VirES", "variant": "FAST", "quality_control": True, "add_APEX": False},
        ("F",),
    )
    code = render_code(_req(spec), CAT)
    ast.parse(code)
    assert "from_VirES=True" in code
    assert "from_FAST=True" in code
    assert "from_HAPI" not in code
    assert "allow_download=True" in code and "allow_load=True" in code


def test_swarm_hapi_oper_omits_flags():
    spec = RequestSpec("swarm.mag_lr", {"sat_id": "B", "source": "HAPI", "variant": "OPER"}, ("F",))
    code = render_code(_req(spec), CAT)
    assert "from_HAPI=True" in code
    assert "from_VirES" not in code
    assert "from_FAST" not in code
    assert "sat_id='B'" in code


def test_multi_dataset_two_docks():
    code = render_code(
        _req(
            RequestSpec("swarm.mag_lr", {"sat_id": "A", "source": "ESA EO", "variant": "OPER"}, ("F",)),
            RequestSpec("indices.ae", {}, ("AE", "AU", "AL")),
        ),
        CAT,
    )
    ast.parse(code)
    assert code.count("db.dock(") == 2
    assert "[v_1_1_0, v_1_1_1]" in code  # AU, AL grouped together


def test_figsize_scales_with_panel_count():
    # ~2 in/panel, floored at the old 8-in height and capped so it never runs away.
    assert figsize_for_panels(0) == (12, 8)
    assert figsize_for_panels(4) == (12, 8)  # typical single Swarm dataset — unchanged
    assert figsize_for_panels(8) == (12, 16)  # two datasets stop crowding
    assert figsize_for_panels(100) == (12, 40)  # capped


def test_multi_dataset_grows_figure_height():
    # Two MAG datasets (4 panels each) → 8 panels → taller figure than a single dataset.
    single = render_code(_req(RequestSpec("swarm.mag_lr", {"sat_id": "A", "source": "ESA EO"})), CAT)
    assert "figure_config={'figsize': (12, 8)}" in single
    two = _req(
        RequestSpec("swarm.mag_lr", {"sat_id": "A", "source": "VirES"}),
        RequestSpec("swarm.mag_lr", {"sat_id": "A", "source": "HAPI"}),
    )
    assert panel_count(two, CAT) == 8
    code = render_code(two, CAT)
    ast.parse(code)
    assert "figure_config={'figsize': (12, 16)}" in code


def test_geomap_scaffold():
    code = render_code(_req(RequestSpec("ampere.fitted")), CAT)
    ast.parse(code)
    assert "GeoDashboard(" in code
    assert "manually downloaded" in code.lower()


def test_dock_kwargs_swarm_vs_other():
    mag = CAT.get("swarm.mag_lr")
    kw = build_dock_kwargs(mag, {"sat_id": "C", "source": "ESA EO", "variant": "OPER", "quality_control": False})
    assert kw["sat_id"] == "C" and kw["allow_load"] is True and "from_VirES" not in kw
    ae = CAT.get("indices.ae")
    assert build_dock_kwargs(ae, {}) == {"load_mode": "AUTO", "allow_load": True}


@pytest.mark.parametrize("pid", [p.id for p in CAT.products.values()])
def test_every_product_generates_valid_python(pid):
    product = CAT.get(pid)
    params = {sp.name: (sp.default if sp.default is not None else (sp.options[0] if sp.options else "")) for sp in product.params}
    code = render_code(_req(RequestSpec(pid, params)), CAT)
    ast.parse(code)
