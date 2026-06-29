"""Typed model for the data-source catalog.

The catalog is declarative YAML (see ``*.yaml`` in this package). It is the single
source of truth for the dropdown directory, the generated code, and the runner. The
only behaviour that cannot be data — which geospacelab class/path builds a product — is
captured by ``loader`` + ``express_target`` / ``datasource_contents`` and resolved in
``registry.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Loader kinds.
EXPRESS = "express"   # geospacelab.express.*Dashboard(...).quicklook()
DATAHUB = "datahub"   # TSDashboard().dock(datasource_contents=...) + set_layout/draw
GEOMAP = "geomap"     # GeoDashboard over a manually downloaded file (cartopy)

# Credential kinds (None == no credentials required).
CREDENTIALS = (None, "esa_eo", "madrigal", "vires")


@dataclass(frozen=True)
class ParamSpec:
    """A single per-product input widget."""

    name: str                      # matches a declared RequestState param
    widget: str = "select"         # select | multiselect | bool | text | int
    options: tuple[Any, ...] | None = None
    default: Any = None
    label: str | None = None
    help: str | None = None

    def __post_init__(self):
        if self.options is not None and not isinstance(self.options, tuple):
            object.__setattr__(self, "options", tuple(self.options))


@dataclass(frozen=True)
class Product:
    """A leaf in the catalog tree: one selectable dataset/product."""

    id: str
    label: str
    category: str
    source: str
    loader: str = DATAHUB
    credential: str | None = None
    # express loader:
    express_target: str | None = None          # "module:Class"
    # datahub / geomap loader:
    datasource_contents: tuple[str, ...] | None = None
    # shared:
    params: tuple[ParamSpec, ...] = ()
    variables: tuple[str, ...] = ()            # selectable variables (datahub)
    default_layout: tuple[tuple[str, ...], ...] = ()  # default panel groups (datahub)
    max_span_hours: float = 72.0
    needs_cartopy: bool = False
    note: str | None = None                    # surfaced in the UI (e.g. preview caveats)

    def param(self, name: str) -> ParamSpec | None:
        for p in self.params:
            if p.name == name:
                return p
        return None

    @property
    def param_names(self) -> list[str]:
        return [p.name for p in self.params]


@dataclass
class Catalog:
    """The whole catalog: products plus the category -> source -> products tree."""

    products: dict[str, Product] = field(default_factory=dict)
    # ordered tree preserving YAML order
    _tree: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    def add(self, product: Product) -> None:
        if product.id in self.products:
            raise ValueError(f"Duplicate product id: {product.id}")
        self.products[product.id] = product
        self._tree.setdefault(product.category, {}).setdefault(product.source, []).append(product.id)

    # --- tree navigation (drives the cascading dropdowns) ---
    def categories(self) -> list[str]:
        return list(self._tree.keys())

    def sources_for(self, category: str) -> list[str]:
        return list(self._tree.get(category, {}).keys())

    def products_for(self, category: str, source: str) -> list[Product]:
        ids = self._tree.get(category, {}).get(source, [])
        return [self.products[i] for i in ids]

    def get(self, product_id: str) -> Product:
        return self.products[product_id]

    def __contains__(self, product_id: str) -> bool:
        return product_id in self.products

    def __len__(self) -> int:
        return len(self.products)
