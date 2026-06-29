"""Reactive dashboard state.

A single ``param.Parameterized`` holds the cascading selection (category -> source group
-> product), the global time range, a fixed superset of per-product input params (only the
active subset is shown), the selected variables, and the list of "added" datasets for
multi-panel plots. Watchers keep the generated code in sync; the live preview is wired to
an explicit Run button (not a watcher) because geospacelab downloads real data.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import param

from . import settings
from .catalog import get_catalog
from .codegen import render_code
from .errors import friendly_error
from .spec import RequestSpec, RunRequest

# Per-product input params (a superset; the active subset comes from the descriptor).
PRODUCT_PARAM_NAMES = [
    "sat_id", "source", "variant", "quality_control", "add_APEX",
    "omni_type", "omni_res", "site", "antenna", "modulation",
    "data_file_type", "load_mode", "pulse_code",
]


class RequestState(param.Parameterized):
    # --- cascade (note: 'source' below is the SWARM backend param, so the cascade's
    # middle level is named source_group to avoid a clash) ---
    category = param.Selector(default=None, objects=[])
    source_group = param.Selector(default=None, objects=[])
    product = param.Selector(default=None, objects=[])

    # --- global time range ---
    dt_fr = param.Date(default=dt.datetime(2015, 3, 17, 0, 0))
    dt_to = param.Date(default=dt.datetime(2015, 3, 18, 0, 0))

    # --- selected variables (datahub products) ---
    variables = param.ListSelector(default=[], objects=[])

    # --- per-product input superset ---
    sat_id = param.Selector(default="A", objects=["A", "B", "C"])
    source = param.Selector(default="ESA EO", objects=["ESA EO", "VirES", "HAPI"])
    variant = param.Selector(default="OPER", objects=["OPER", "FAST"])
    quality_control = param.Boolean(default=True)
    add_APEX = param.Boolean(default=False)
    omni_type = param.Selector(default="OMNI2", objects=["OMNI2", "OMNI1"])
    omni_res = param.Selector(default="1min", objects=["1min", "5min", "1hour"])
    site = param.Selector(default="TRO", objects=["TRO", "KIR", "SOD", "ESR"])
    antenna = param.Selector(default="UHF", objects=["UHF", "VHF", "42m", "32m"])
    modulation = param.String(default="")
    data_file_type = param.Selector(default="madrigal-hdf5", objects=["madrigal-hdf5", "eiscat-hdf5"])
    load_mode = param.Selector(default="AUTO", objects=["AUTO"])
    pulse_code = param.Selector(default="single pulse", objects=["single pulse", "alternating code"])

    # --- added datasets (multi-panel) ---
    datasets = param.List(default=[])

    # --- outputs ---
    code = param.String(default="")
    error_msg = param.String(default="")
    is_running = param.Boolean(default=False)
    preview_fig = param.Parameter(default=None)
    data_repr = param.String(default="")
    console_log = param.String(default="")
    active_param_names = param.List(default=[])

    def __init__(self, catalog=None, **params):
        super().__init__(**params)
        self.catalog = catalog or get_catalog()
        self._task = None
        self._suspend = True
        # Seed the cascade.
        self.param.category.objects = self.catalog.categories()
        self.category = self.catalog.categories()[0]
        self._on_category()
        # Wire watchers after initial population.
        self.param.watch(self._on_category, "category")
        self.param.watch(self._on_source_group, "source_group")
        self.param.watch(self._on_product, "product")
        self.param.watch(self._regen, ["product", "dt_fr", "dt_to", "variables", "datasets", *PRODUCT_PARAM_NAMES])
        self._suspend = False
        self._regen()

    # --- cascade handlers ---
    def _on_category(self, *_):
        groups = self.catalog.sources_for(self.category)
        with self._suspended():
            self.param.source_group.objects = groups
            self.source_group = groups[0]
        self._on_source_group()

    def _on_source_group(self, *_):
        products = self.catalog.products_for(self.category, self.source_group)
        labels = {p.label: p.id for p in products}
        with self._suspended():
            self.param.product.objects = labels
            self.product = products[0].id
        self._on_product()

    def _on_product(self, *_):
        product = self.catalog.get(self.product)
        with self._suspended():
            for p in product.params:
                pobj = self.param[p.name]
                if p.options is not None and hasattr(pobj, "objects"):
                    pobj.objects = list(p.options)
                default = p.default if p.default is not None else (p.options[0] if p.options else None)
                if default is not None:
                    try:
                        setattr(self, p.name, default)
                    except ValueError:
                        pass
            self.param.variables.objects = list(product.variables)
            self.variables = [v for grp in product.default_layout for v in grp]
            self.active_param_names = product.param_names
        self._regen()

    # --- code regeneration ---
    def _regen(self, *_):
        if self._suspend:
            return
        self.code = render_code(self.current_request(), self.catalog)

    # --- request assembly ---
    @property
    def active_product(self):
        return self.catalog.get(self.product)

    def current_spec(self) -> RequestSpec:
        params = {n: getattr(self, n) for n in self.active_param_names}
        return RequestSpec(self.product, params, tuple(self.variables))

    def current_request(self) -> RunRequest:
        specs = tuple(self.datasets) or (self.current_spec(),)
        return RunRequest(specs, self.dt_fr, self.dt_to)

    # --- multi-dataset management ---
    def add_dataset(self, *_):
        self.datasets = list(self.datasets) + [self.current_spec()]

    def remove_dataset(self, index: int):
        ds = list(self.datasets)
        if 0 <= index < len(ds):
            ds.pop(index)
            self.datasets = ds

    def clear_datasets(self, *_):
        self.datasets = []

    # --- preview (explicit Run; async so the Bokeh loop stays responsive) ---
    async def run_preview(self, *_):
        if self.is_running:
            return
        self.is_running = True
        self.error_msg = ""
        req = self.current_request()
        try:
            from .runner import build_and_render

            self._task = asyncio.ensure_future(asyncio.to_thread(build_and_render, req, self.catalog))
            result = await asyncio.wait_for(self._task, timeout=settings.PREVIEW_TIMEOUT_SECONDS)
            self.console_log = result.log or ""
            if result.error:
                self.error_msg, self.preview_fig, self.data_repr = result.error, None, ""
            else:
                self.preview_fig, self.data_repr, self.error_msg = result.fig, result.data_repr, ""
        except asyncio.CancelledError:
            self.error_msg = "Preview stopped. (A background download may still be finishing.)"
            self.preview_fig = None
        except asyncio.TimeoutError:
            self.error_msg = f"Preview timed out after {settings.PREVIEW_TIMEOUT_SECONDS}s. Shorten the time range."
        except Exception as exc:  # noqa: BLE001
            self.error_msg = friendly_error(exc)
        finally:
            self.is_running = False
            self._task = None

    def stop_preview(self, *_):
        task = self._task
        if task is not None and not task.done():
            task.cancel()

    # --- helpers ---
    def _suspended(self):
        state = self

        class _Ctx:
            def __enter__(self):
                self.prev = state._suspend
                state._suspend = True

            def __exit__(self, *exc):
                state._suspend = self.prev

        return _Ctx()
