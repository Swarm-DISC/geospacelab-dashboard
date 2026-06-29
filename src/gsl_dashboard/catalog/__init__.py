"""Load and merge the YAML catalog files into a typed :class:`Catalog`.

All ``*.yaml`` files in this package are merged (categories with the same name are
combined). Products may declare their inputs inline via ``params:`` or by referencing a
shared ``param_profile`` (defined below). The result is fully offline — no geospacelab
import required — so the catalog is unit-testable without the heavy stack.
"""

from __future__ import annotations

import functools
import pathlib

import yaml

from .models import DATAHUB, Catalog, ParamSpec, Product

_CATALOG_DIR = pathlib.Path(__file__).resolve().parent

# Shared parameter sets referenced by ``param_profile`` in the YAML.
PARAM_PROFILES: dict[str, list[ParamSpec]] = {
    # Every SWARM product shares these. ``source``/``variant`` are translated to
    # geospacelab dock kwargs (from_VirES/from_HAPI/from_FAST) by codegen/runner.
    "swarm": [
        ParamSpec("sat_id", "select", ("A", "B", "C"), "A", "Satellite"),
        ParamSpec("source", "select", ("ESA EO", "VirES", "HAPI"), "ESA EO", "Source backend"),
        ParamSpec("variant", "select", ("OPER", "FAST"), "OPER", "Variant"),
        # Off by default: some products lack the quality-filter method geospacelab calls.
        ParamSpec("quality_control", "bool", None, False, "Quality control"),
        ParamSpec("add_APEX", "bool", None, False, "Add APEX magnetic coords"),
    ],
}


def _param_from_dict(d: dict) -> ParamSpec:
    return ParamSpec(
        name=d["name"],
        widget=d.get("widget", "select"),
        options=tuple(d["options"]) if d.get("options") is not None else None,
        default=d.get("default"),
        label=d.get("label"),
        help=d.get("help"),
    )


def _resolve_params(prod: dict) -> tuple[ParamSpec, ...]:
    if "param_profile" in prod:
        profile = PARAM_PROFILES[prod["param_profile"]]
        return tuple(profile)
    return tuple(_param_from_dict(p) for p in prod.get("params", []))


def _as_layout(raw) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(group) for group in (raw or ()))


def _build_product(category: str, source: str, prod: dict) -> Product:
    return Product(
        id=prod["id"],
        label=prod["label"],
        category=category,
        source=source,
        loader=prod.get("loader", DATAHUB),
        credential=prod.get("credential"),
        express_target=prod.get("express_target"),
        datasource_contents=tuple(prod["datasource_contents"]) if prod.get("datasource_contents") else None,
        params=_resolve_params(prod),
        variables=tuple(prod.get("variables") or ()),
        default_layout=_as_layout(prod.get("default_layout")),
        max_span_hours=float(prod.get("max_span_hours", 72.0)),
        needs_cartopy=bool(prod.get("needs_cartopy", False)),
        note=prod.get("note"),
    )


def load_catalog(catalog_dir: pathlib.Path | None = None) -> Catalog:
    catalog_dir = catalog_dir or _CATALOG_DIR
    catalog = Catalog()
    for path in sorted(catalog_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        for cat in doc.get("categories", []):
            cat_name = cat["name"]
            for src in cat.get("sources", []):
                src_name = src["name"]
                for prod in src.get("products", []):
                    catalog.add(_build_product(cat_name, src_name, prod))
    return catalog


@functools.lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """Cached catalog singleton for the running app."""
    return load_catalog()
