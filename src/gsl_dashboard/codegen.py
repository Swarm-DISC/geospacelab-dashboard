"""Generate runnable geospacelab code from a :class:`RunRequest`.

Pure and import-light (no geospacelab). Two templates:

* ``express`` — a single ``geospacelab.express.*Dashboard(...).quicklook()`` one-liner.
* ``datahub`` — a ``TSDashboard`` with one ``dock(...)`` per dataset, ``assign_variable``
  references, and a ``panel_layouts`` grid. Used for indices, SWARM, and any multi-dataset
  combination (express dashboards are single-source and can't be combined).

``geomap`` products (AMPERE/SuperDARN/SSUSI) render an honest, commented scaffold.

The param -> kwargs translators (:func:`build_express_kwargs`, :func:`build_dock_kwargs`)
are imported by the runner so the code we *show* and the code we *run* stay identical.
"""

from __future__ import annotations

import datetime as dt

from .catalog.models import EXPRESS, GEOMAP, Product
from .catalog.registry import parse_target
from .spec import RequestSpec, RunRequest


def _fmt_dt(d: dt.datetime) -> str:
    return f"datetime.datetime({d.year}, {d.month}, {d.day}, {d.hour}, {d.minute})"


def _is_swarm(product: Product) -> bool:
    dsc = product.datasource_contents or ()
    return len(dsc) >= 2 and dsc[0] == "esa_eo" and dsc[1] == "swarm"


# --- param -> kwargs translation (shared with runner.py) --------------------------

def build_express_kwargs(product: Product, params: dict) -> dict:
    """Active params passed straight through to the express constructor."""
    out = {}
    for p in product.params:
        if p.name in params:
            out[p.name] = params[p.name]
    return out


def build_dock_kwargs(product: Product, params: dict) -> dict:
    """Translate the active params into ``dock()`` kwargs for a datahub/geomap product."""
    out: dict = {}
    if _is_swarm(product):
        out["sat_id"] = params.get("sat_id", "A")
        if "quality_control" in params:
            out["quality_control"] = bool(params["quality_control"])
        if params.get("add_APEX"):
            out["add_APEX"] = True
        source = params.get("source", "ESA EO")
        if source == "VirES":
            out["from_VirES"] = True
        elif source == "HAPI":
            out["from_HAPI"] = True
        if params.get("variant") == "FAST":
            out["from_FAST"] = True
        # SWARM datasets don't auto-load/download by default.
        out["allow_download"] = True
        out["allow_load"] = True
    else:
        out["load_mode"] = "AUTO"
        out["allow_load"] = True
    return out


def _layout_groups(product: Product, selected) -> list[list[str]]:
    """Panel groups: keep the product's default groupings for selected vars, then append
    any remaining selected vars as their own panels."""
    selected = list(selected)
    sel = set(selected)
    groups: list[list[str]] = []
    covered: set[str] = set()
    for grp in product.default_layout:
        keep = [v for v in grp if v in sel]
        if keep:
            groups.append(keep)
            covered.update(keep)
    for v in selected:
        if v not in covered:
            groups.append([v])
            covered.add(v)
    return groups


def _selected_or_default(product: Product, spec: RequestSpec) -> list[str]:
    if spec.variables:
        return list(spec.variables)
    return [v for grp in product.default_layout for v in grp]


def _kwargs_inline(kwargs: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in kwargs.items())


# --- templates --------------------------------------------------------------------

def _render_express(req: RunRequest, product: Product) -> str:
    spec = req.datasets[0]
    module, cls = parse_target(product.express_target)
    kwargs = build_express_kwargs(product, spec.params)
    lines = [
        "import datetime",
        f"from {module} import {cls}",
        "",
        f"dt_fr = {_fmt_dt(req.dt_fr)}",
        f"dt_to = {_fmt_dt(req.dt_to)}",
        "",
        f"dashboard = {cls}(",
        "    dt_fr, dt_to,",
    ]
    for k, v in kwargs.items():
        lines.append(f"    {k}={v!r},")
    lines += [
        ")",
        "dashboard.quicklook()",
        "dashboard.show()",
    ]
    return "\n".join(lines) + "\n"


def _render_datahub(req: RunRequest, catalog) -> str:
    lines = [
        "import datetime",
        "from geospacelab.visualization.mpl.dashboards import TSDashboard",
        "",
        f"dt_fr = {_fmt_dt(req.dt_fr)}",
        f"dt_to = {_fmt_dt(req.dt_to)}",
        "",
        "db = TSDashboard(dt_fr=dt_fr, dt_to=dt_to, figure_config={'figsize': (12, 8)})",
        "",
    ]
    panels: list[list[str]] = []
    for i, spec in enumerate(req.datasets):
        product = catalog.get(spec.dataset_id)
        if product.loader == EXPRESS:
            lines.append(f"# NOTE: {product.label!r} is an express quicklook and cannot be combined here; skipped.")
            continue
        if product.loader == GEOMAP:
            lines.append(f"# NOTE: {product.label!r} needs a manual map setup; use its single-dataset view.")
            continue
        dock_kw = build_dock_kwargs(product, spec.params)
        lines.append(
            f"ds_{i} = db.dock(datasource_contents={list(product.datasource_contents)!r}, {_kwargs_inline(dock_kw)})"
        )
        groups = _layout_groups(product, _selected_or_default(product, spec))
        for j, group in enumerate(groups):
            refs = []
            for k, var in enumerate(group):
                ref = f"v_{i}_{j}_{k}"
                lines.append(f"{ref} = db.assign_variable({var!r}, dataset=ds_{i})")
                refs.append(ref)
            panels.append(refs)
        lines.append("")
    if panels:
        lines.append("panel_layouts = [")
        for refs in panels:
            lines.append("    [" + ", ".join(refs) + "],")
        lines.append("]")
        lines.append("db.set_layout(panel_layouts=panel_layouts)")
        lines.append("db.draw()")
        if req.title:
            lines.append(f"db.add_title(title={req.title!r})")
    else:
        lines.append("# No variables selected to plot.")
    lines.append("db.show()")
    return "\n".join(lines) + "\n"


def _render_geomap(req: RunRequest, product: Product) -> str:
    dsc = list(product.datasource_contents or [])
    return (
        "import datetime\n"
        "from geospacelab.visualization.mpl.geomap.geodashboards import GeoDashboard\n"
        "\n"
        f"dt_fr = {_fmt_dt(req.dt_fr)}\n"
        f"dt_to = {_fmt_dt(req.dt_to)}\n"
        "\n"
        f"# {product.label}: not an express dashboard.\n"
        f"# Requires cartopy and (for AMPERE/SuperDARN) a manually downloaded file.\n"
        "db = GeoDashboard(dt_fr=dt_fr, dt_to=dt_to, figure_config={'figsize': (8, 8)})\n"
        f"ds = db.dock(datasource_contents={dsc!r})  # configure the local file / download manually\n"
        "# panel = db.add_polar_map(row_ind=0, col_ind=0, pole='N')\n"
        "# ... plot the variable of interest onto the map ...\n"
        "db.show()\n"
    )


def render_code(req: RunRequest, catalog) -> str:
    """Render runnable geospacelab code for ``req`` using ``catalog`` for descriptors."""
    if not req.datasets:
        return "# Select a dataset to generate code.\n"
    if req.is_single:
        product = catalog.get(req.datasets[0].dataset_id)
        if product.loader == EXPRESS:
            return _render_express(req, product)
        if product.loader == GEOMAP:
            return _render_geomap(req, product)
    return _render_datahub(req, catalog)
