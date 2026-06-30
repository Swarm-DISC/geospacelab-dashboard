"""Generate src/gsl_dashboard/catalog/sources_swarm.yaml from the installed geospacelab.

AST-parses each SWARM product's ``default_variable_names`` (no data is loaded), groups
products by instrument, and attaches the shared SWARM parameter block (sat_id, source,
variant, quality_control, add_APEX). Re-run after upgrading geospacelab; the
``test_catalog_introspection`` test verifies the committed YAML still matches the package.

Run: .venv/bin/python scripts/gen_swarm_catalog.py
"""

import ast
import pathlib
import re

import geospacelab

GSL = pathlib.Path(geospacelab.__file__).parent
SWARM = GSL / "datahub" / "sources" / "esa_eo" / "swarm"
OUT = pathlib.Path(__file__).resolve().parent.parent / "src" / "gsl_dashboard" / "catalog" / "sources_swarm.yaml"

LEVELS = ["l1b", "advanced", "l2daily"]

# Map product code -> (source group name, friendly label).
GROUPS = {
    "mag_lr": ("Magnetic field (MAG)", "MAG low-rate 1 Hz B-field (L1b)"),
    "mag_hr": ("Magnetic field (MAG)", "MAG high-rate 50 Hz B-field (L1b)"),
    "efi_lp": ("Electric field (EFI)", "EFI Langmuir Probe (L1b)"),
    "efi_lpi": ("Electric field (EFI)", "EFI Langmuir Probe, ion (L1b)"),
    "efi_idm": ("Electric field (EFI)", "EFI Ion Drift Meter (advanced)"),
    "efi_lp_fp": ("Electric field (EFI)", "EFI LP face-plate (advanced)"),
    "efi_lp_hm": ("Electric field (EFI)", "EFI LP high-rate plasma (advanced)"),
    "efi_tct02": ("Electric field (EFI)", "EFI TII cross-track flow 2 Hz (advanced)"),
    "efi_tct16": ("Electric field (EFI)", "EFI TII cross-track flow 16 Hz (advanced)"),
    "efi_tie": ("Electric field (EFI)", "EFI TII ion temperature"),
    "aej_lpl": ("Currents & auroral electrojets", "Auroral electrojets — line profile (LPL)"),
    "aej_lps": ("Currents & auroral electrojets", "Auroral electrojets — peaks (LPS)"),
    "aej_pbl": ("Currents & auroral electrojets", "Auroral electrojet boundaries (PBL)"),
    "aej_pbs": ("Currents & auroral electrojets", "Auroral electrojet boundaries (PBS)"),
    "aob_fac": ("Currents & auroral electrojets", "Auroral oval boundaries from FAC"),
    "fac_tms": ("Currents & auroral electrojets", "Field-aligned currents, single-sat"),
    "fac_tms_dual": ("Currents & auroral electrojets", "Field-aligned currents, dual-sat"),
    "fac_lls_dual": ("Currents & auroral electrojets", "Field-aligned currents LLS, dual-sat"),
    "ppi_fac": ("Currents & auroral electrojets", "Plasmapause-related boundary (PPI)"),
    "ibi_tms": ("Ionosphere", "Ionospheric bubble index (IBI)"),
    "ipd_irr": ("Ionosphere", "Ionospheric plasma irregularities (IPD)"),
    "tec_tms": ("Ionosphere", "Total electron content (TEC)"),
    "tix_tms": ("Ionosphere", "Topside ionosphere index (TIX)"),
    "nix_tms": ("Ionosphere", "Nitrogen index (NIX)"),
    "mit_lp": ("Ionosphere", "Midlatitude trough from LP (MIT_LP)"),
    "mit_tec": ("Ionosphere", "Midlatitude trough from TEC (MIT_TEC)"),
    "eef_tms": ("Ionosphere", "Equatorial electric field (EEF)"),
    "dns_acc": ("Thermosphere", "Neutral density, accelerometer (DNS_ACC)"),
    "dns_pod": ("Thermosphere", "Neutral density, POD (DNS_POD)"),
    "whi_evt": ("Waves", "Whistler-mode chorus events (WHI)"),
}

# Names excluded from the *default panel layout* (still selectable as variables):
# spacecraft coordinates/time (SC_*), magnetic-perturbation breakdowns (dB_*), flags,
# and other housekeeping. The science variables don't carry these prefixes.
_SKIP_LAYOUT = re.compile(
    r"^(SC_|dB_|FLAG|STATUS|SYNC|QUALITY|BOUNDARY|PAIR|Counter|CALIB|CDF_EPOCH|DATETIME|GEO_"
    r"|APEX_|AACGM_|MLT|MLAT|QD_|POS_|Distance|Azimuth|TimeFrac|dL)",
)

# Curated default panels for products where the first few science variables aren't the
# most useful (e.g. prefer NEC field components + intensity over instrument-frame B_VFM).
LAYOUT_OVERRIDES = {
    "mag_lr": ["F", "B_N", "B_E", "B_C"],
    "mag_hr": ["F", "B_N", "B_E", "B_C"],
    "whi_evt": ["Whistler_Dispersion", "Whistler_t0", "Intensity", "F_analysed"],
}

# Preferred ordering within a source group (lower = earlier). The first product in a
# group becomes the UI default, so surface MAG low-rate before high-rate. Products not
# listed keep their alphabetical order (the sort is stable).
PRODUCT_ORDER = {"swarm.mag_lr": 0, "swarm.mag_hr": 1}

# Products whose upstream variable_config.py is a wrong copy of another product's, so
# plottable_vars() would return the wrong variables. As of geospacelab 0.14.15, whi_evt
# ships tec_tms's variable_config.py verbatim — derive its variables from the product's
# own default_variable_names (in __init__.py) instead. Revisit when geospacelab fixes it.
BROKEN_VARIABLE_CONFIG = {"whi_evt"}


def _skip_for_layout(name: str) -> bool:
    return bool(_SKIP_LAYOUT.match(name)) or name.endswith(("_err", "_Sigma", "_uncertainty", "_AUX", "_IND"))


def _literal_list_assign(tree, names) -> list[str]:
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Set, ast.Tuple)):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    # Read elements in source order. A set literal (e.g. whi_evt's
                    # default_variable_names) is unordered at runtime, but its source order
                    # is stable — keeps the generated YAML deterministic across runs.
                    found[t.id] = [
                        e.value for e in node.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    ]
    for name in names:  # honour priority order
        if found.get(name):
            return found[name]
    return []


def _var_names_from_config(prod_dir: pathlib.Path) -> list[str]:
    """Fallback: collect ``var_name = '...'`` strings from variable_config.py."""
    cfg = prod_dir / "variable_config.py"
    if not cfg.is_file():
        return []
    out = []
    tree = ast.parse(cfg.read_text(errors="ignore"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "var_name"
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            out.append(node.value.value)
    # de-dupe preserving order
    return list(dict.fromkeys(out))


def plottable_vars(prod_dir: pathlib.Path) -> list[str]:
    """Variables safe to drop into a TSDashboard time-series panel.

    A variable qualifies only if it is (a) registered in ``configured_variables``,
    (b) given a non-None ``plot_config.style``, and (c) carries a standard UT time
    dependence (``var.depends = {0: depend_X}`` where ``depend_X`` has a ``'UT'`` key).

    This excludes two crash/warning classes:
      * raw vector arrays (B_VFM, B_NEC) — never configured at all (style is None) → the
        loader splits them into scalars (B_VFM_x/y/z, B_N/B_E/B_C);
      * variables on a secondary time grid (e.g. AEJ_LPL's RMS_MISFIT / CONFIDENCE use a
        ``'UT_QUAL'`` key on DATETIME_QUAL) → "The dependence on UT is not set!".
    """
    cfg = prod_dir / "variable_config.py"
    if not cfg.is_file():
        return []
    try:
        tree = ast.parse(cfg.read_text(errors="ignore"))
    except SyntaxError:
        return []

    # Which module-level ``depend_*`` dicts carry a standard 'UT' key.
    depend_has_ut: dict[str, bool] = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.startswith("depend")
                and isinstance(node.value, ast.Dict)):
            keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
            depend_has_ut[node.targets[0].id] = "UT" in keys

    current = None
    styles: dict[str, str] = {}
    var_depend: dict[str, str] = {}
    registered: list[str] = []
    seen: set[str] = set()
    for node in tree.body:  # source order matters for tracking the current var_name
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if isinstance(tgt, ast.Name) and tgt.id == "var_name" and isinstance(node.value, ast.Constant):
            current = node.value.value
        elif isinstance(tgt, ast.Attribute) and tgt.attr == "style" \
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if current:
                styles[current] = node.value.value
        elif isinstance(tgt, ast.Attribute) and tgt.attr == "depends" and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == 0 and isinstance(v, ast.Name) and current:
                    var_depend[current] = v.id
        elif isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name) \
                and tgt.value.id == "configured_variables":
            key = tgt.slice
            name = key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else current
            if name and name not in seen:
                seen.add(name)
                registered.append(name)

    out = []
    for n in registered:
        if n not in styles:
            continue
        dep = var_depend.get(n)
        if dep is not None and dep in depend_has_ut and not depend_has_ut[dep]:
            continue  # has a known non-UT (e.g. UT_QUAL) dependence -> not time-series plottable
        out.append(n)
    return out


def parse_var_names(prod_dir: pathlib.Path) -> list[str]:
    # Prefer the configured + styled (plottable) variables; fall back to the declared
    # default names only if a product has no parseable variable_config (or ships a wrong
    # one — see BROKEN_VARIABLE_CONFIG).
    if prod_dir.name not in BROKEN_VARIABLE_CONFIG:
        plottable = plottable_vars(prod_dir)
        if plottable:
            return plottable
    init_path = prod_dir / "__init__.py"
    tree = ast.parse(init_path.read_text(errors="ignore"))
    names = _literal_list_assign(
        tree, ["default_variable_names", "default_variable_names_0502", "default_variable_names_old"]
    )
    return names or _var_names_from_config(prod_dir)


def collect() -> dict[str, list[dict]]:
    by_group: dict[str, list[dict]] = {}
    for level in LEVELS:
        level_dir = SWARM / level
        if not level_dir.is_dir():
            continue
        for prod_dir in sorted(level_dir.iterdir()):
            if not prod_dir.is_dir() or prod_dir.name.startswith("__"):
                continue
            code = prod_dir.name
            if code not in GROUPS:
                continue
            group, label = GROUPS[code]
            var_names = parse_var_names(prod_dir)
            plot_vars = [v for v in var_names if not _skip_for_layout(v)]
            override = [v for v in LAYOUT_OVERRIDES.get(code, []) if v in var_names]
            chosen = override or plot_vars[:4]
            layout = [[v] for v in chosen] or ([[var_names[0]]] if var_names else [])
            by_group.setdefault(group, []).append({
                "id": f"swarm.{code}",
                "label": label,
                "dsc": ["esa_eo", "swarm", level, code],
                "variables": var_names,
                "layout": layout,
            })
    for prods in by_group.values():  # surface preferred products first (stable)
        prods.sort(key=lambda p: PRODUCT_ORDER.get(p["id"], 50))
    return by_group


def fmt_list(items) -> str:
    return "[" + ", ".join(items) + "]"


def emit(by_group: dict[str, list[dict]]) -> str:
    lines = [
        "# AUTO-GENERATED by scripts/gen_swarm_catalog.py from geospacelab "
        + geospacelab.__version__ + ".",
        "# Do not edit by hand: datasource_contents and variables come from the installed package.",
        "categories:",
        "  - name: Swarm",
        "    sources:",
    ]
    for group, prods in by_group.items():
        lines.append(f"      - name: {yaml_str(group)}")
        lines.append("        products:")
        for p in prods:
            lines.append(f"          - id: {p['id']}")
            lines.append(f"            label: {yaml_str(p['label'])}")
            lines.append("            loader: datahub")
            lines.append("            credential: esa_eo")
            lines.append(f"            datasource_contents: {fmt_list(p['dsc'])}")
            lines.append("            max_span_hours: 24")
            lines.append("            param_profile: swarm")
            lines.append("            variables:")
            for v in p["variables"]:
                lines.append(f"              - {yaml_str(v)}")
            if p["layout"]:
                lines.append("            default_layout:")
                for grp in p["layout"]:
                    lines.append(f"              - {fmt_list([yaml_str(v) for v in grp])}")
    return "\n".join(lines) + "\n"


def yaml_str(s: str) -> str:
    # Quote anything that isn't a plain scalar.
    if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_ ./()-]*", s) and not s.endswith(" "):
        return s
    return "'" + s.replace("'", "''") + "'"


if __name__ == "__main__":
    OUT.write_text(emit(collect()))
    n = sum(len(v) for v in collect().values())
    print(f"Wrote {n} SWARM products across {len(collect())} groups to {OUT}")
