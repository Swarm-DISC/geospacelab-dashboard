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
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import param

from . import settings
from .catalog import get_catalog
from .codegen import render_code
from .errors import friendly_error
from .spec import RequestSpec, RunRequest

_WORKER_SCRIPT = str(Path(__file__).resolve().parent / "preview_worker.py")

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

    # --- global time range (default to a 1-hour window — fast to download/preview) ---
    dt_fr = param.Date(default=dt.datetime(2015, 3, 17, 0, 0))
    dt_to = param.Date(default=dt.datetime(2015, 3, 17, 1, 0))

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
    preview_png = param.Parameter(default=None)  # rendered PNG bytes (built in a subprocess)
    data_repr = param.String(default="")
    console_log = param.String(default="")
    active_param_names = param.List(default=[])

    def __init__(self, catalog=None, **params):
        super().__init__(**params)
        self.catalog = catalog or get_catalog()
        self._proc = None
        self._stop_requested = False
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

    # --- preview (explicit Run) ---
    # The render runs in a child process (preview_worker.py) so Stop can genuinely abort an
    # in-flight download: terminating the process closes its sockets. The async wrapper just
    # parks the blocking wait on a worker thread so the Bokeh loop stays responsive.
    async def run_preview(self, *_):
        if self.is_running:
            return
        self.is_running = True
        self.error_msg = ""
        self._stop_requested = False
        req = self.current_request()
        try:
            result = await asyncio.to_thread(self._run_worker, req)
            self.console_log = result.get("log") or ""
            if result.get("stopped"):
                self.preview_png, self.data_repr, self.error_msg = None, "", "Preview stopped."
            elif result.get("error"):
                self.preview_png, self.data_repr, self.error_msg = None, "", result["error"]
            else:
                self.preview_png = result.get("png")
                self.data_repr = result.get("data_repr") or ""
                self.error_msg = ""
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self.error_msg = friendly_error(exc)
        finally:
            self.is_running = False
            self._proc = None

    def _run_worker(self, req) -> dict:
        """Blocking (runs on a worker thread): render the preview in a killable child
        process. Returns a result dict with one of png / error / stopped, plus log."""
        tmp = tempfile.mkdtemp(prefix="gsl-preview-")
        in_path = os.path.join(tmp, "request.pkl")
        out_path = os.path.join(tmp, "result.pkl")
        log_path = os.path.join(tmp, "worker.log")
        try:
            with open(in_path, "wb") as f:
                pickle.dump(req, f)
            with open(log_path, "wb") as logf:  # child keeps its own dup of the fd
                proc = subprocess.Popen(
                    [sys.executable, _WORKER_SCRIPT, in_path, out_path],
                    stdout=logf, stderr=subprocess.STDOUT,
                )
            self._proc = proc
            try:
                proc.wait(timeout=settings.PREVIEW_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                return {"error": f"Preview timed out after {settings.PREVIEW_TIMEOUT_SECONDS}s. "
                                 "Shorten the time range."}
            if self._stop_requested:
                return {"stopped": True}
            if proc.returncode == 0 and os.path.exists(out_path):
                with open(out_path, "rb") as f:
                    return pickle.load(f)
            tail = Path(log_path).read_text(errors="ignore")[-3000:]
            return {"error": "The preview process exited unexpectedly.", "log": tail}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def stop_preview(self, *_):
        # Signal a kill; the worker thread reaps the process and reports "stopped". Only send
        # the signal here (the worker thread owns wait()), to avoid a cross-thread double-wait.
        self._stop_requested = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

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
