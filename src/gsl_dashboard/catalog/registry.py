"""Resolve catalog string references to importable geospacelab objects.

Kept tiny and lazy: geospacelab is only imported when a product is actually executed,
never at catalog-load time. This is the single place that maps declarative catalog data
to executable behaviour.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .models import Product


def parse_target(express_target: str) -> tuple[str, str]:
    """``"module.path:ClassName"`` -> ``("module.path", "ClassName")``."""
    module, _, cls = express_target.partition(":")
    if not module or not cls:
        raise ValueError(f"Invalid express_target {express_target!r}; expected 'module:Class'.")
    return module, cls


def import_express_class(express_target: str):
    module_name, cls_name = parse_target(express_target)
    module = importlib.import_module(module_name)
    return getattr(module, cls_name)


def express_class_for(product: "Product"):
    if not product.express_target:
        raise ValueError(f"Product {product.id} has no express_target.")
    return import_express_class(product.express_target)
