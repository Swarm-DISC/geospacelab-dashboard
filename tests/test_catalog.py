"""Offline catalog integrity checks (no geospacelab import)."""

import param

from gsl_dashboard.catalog import get_catalog
from gsl_dashboard.catalog.models import CREDENTIALS, DATAHUB, EXPRESS, GEOMAP
from gsl_dashboard.catalog.registry import parse_target
from gsl_dashboard.state import RequestState

CAT = get_catalog()


def test_catalog_non_empty():
    assert len(CAT) > 30  # ~30 SWARM + curated sources


def test_ids_unique():
    ids = [p.id for p in CAT.products.values()]
    assert len(ids) == len(set(ids))


def test_loader_requirements():
    for p in CAT.products.values():
        assert p.loader in (EXPRESS, DATAHUB, GEOMAP)
        assert p.credential in CREDENTIALS
        if p.loader == EXPRESS:
            assert p.express_target, p.id
            module, cls = parse_target(p.express_target)
            assert module and cls
        else:
            assert p.datasource_contents, p.id


def test_default_layout_vars_are_known():
    for p in CAT.products.values():
        flat = {v for grp in p.default_layout for v in grp}
        assert flat <= set(p.variables), f"{p.id}: layout vars not in variables"


def test_param_names_are_declared_state_params():
    declared = set(RequestState.param)
    for p in CAT.products.values():
        for spec in p.params:
            assert spec.name in declared, f"{p.id}: param {spec.name} not on RequestState"


def test_param_defaults_in_options():
    for p in CAT.products.values():
        for spec in p.params:
            if spec.options is not None and spec.default is not None:
                assert spec.default in spec.options, f"{p.id}.{spec.name}"


def test_swarm_products_have_swarm_profile():
    swarm = [p for p in CAT.products.values() if p.id.startswith("swarm.")]
    assert len(swarm) >= 28
    for p in swarm:
        names = p.param_names
        assert {"sat_id", "source", "variant"} <= set(names), p.id


def test_no_raw_vector_variables_in_swarm():
    """Raw vector arrays (B_NEC, B_VFM, *_NEC, *_VFM) are not plottable in a panel and
    crash db.draw(); only their scalar components may appear."""
    bad = {"B_NEC", "B_VFM"}
    for p in CAT.products.values():
        if not p.id.startswith("swarm."):
            continue
        for v in p.variables:
            assert v not in bad and not v.endswith(("_NEC", "_VFM")), f"{p.id}: raw vector {v}"
        for grp in p.default_layout:
            for v in grp:
                assert v not in bad and not v.endswith(("_NEC", "_VFM")), f"{p.id}: layout has raw vector {v}"


def test_mag_lr_layout_is_nec_components():
    layout = [v for grp in CAT.get("swarm.mag_lr").default_layout for v in grp]
    assert layout == ["F", "B_N", "B_E", "B_C"]


def test_mag_group_defaults_to_low_rate():
    """The first product in a source group is the UI default; MAG should default to
    low-rate (the common baseline), not high-rate."""
    mag = CAT.products_for("Swarm", "Magnetic field (MAG)")
    assert mag[0].id == "swarm.mag_lr"
    assert {"swarm.mag_lr", "swarm.mag_hr"} <= {p.id for p in mag}


def test_alt_source_backends_only_for_mag_lr():
    """Only swarm.mag_lr supports VirES/HAPI in geospacelab; the UI greys them out
    elsewhere via disabled_source_backends()."""
    from gsl_dashboard.catalog import disabled_source_backends

    assert disabled_source_backends("swarm.mag_lr") == []
    assert disabled_source_backends("swarm.mag_hr") == ["VirES", "HAPI"]
    assert disabled_source_backends("swarm.efi_lp") == ["VirES", "HAPI"]
    assert disabled_source_backends(None) == ["VirES", "HAPI"]


def test_whi_evt_has_whistler_variables_not_tec():
    """geospacelab 0.14.15 ships tec_tms's variable_config.py for whi_evt, so the generator
    must derive whi_evt's variables from its own default_variable_names instead (else the
    catalog lists GPS/TEC variables). See BROKEN_VARIABLE_CONFIG in gen_swarm_catalog.py."""
    whi = CAT.get("swarm.whi_evt")
    assert {"Whistler_Dispersion", "Whistler_t0", "Intensity", "F_analysed"} <= set(whi.variables)
    # No leakage of TEC/GPS variables from the wrong upstream config.
    assert not ({"VTEC_ABS", "STEC_ABS", "PRN", "DCB", "EL"} & set(whi.variables))
    assert [v for grp in whi.default_layout for v in grp] == [
        "Whistler_Dispersion", "Whistler_t0", "Intensity", "F_analysed",
    ]


def test_secondary_time_grid_vars_excluded():
    """AEJ_LPL's RMS_MISFIT / CONFIDENCE live on a secondary time grid (UT_QUAL) and
    cannot be plotted in a UT panel ("dependence on UT is not set")."""
    aej = CAT.get("swarm.aej_lpl")
    assert "RMS_MISFIT" not in aej.variables
    assert "CONFIDENCE" not in aej.variables
    assert [v for grp in aej.default_layout for v in grp] == ["J_N", "J_E", "J_QD"]
