"""Execute a :class:`RunRequest` against geospacelab and capture a matplotlib figure.

A *structured builder*, not ``exec()`` of the generated string: safer (no arbitrary code
in the server), testable, and able to inject guardrails the documentary snippet shouldn't
carry. It consumes the same :class:`RunRequest` and the same param->kwargs translators as
``codegen`` so the previewed plot matches the shown code.

geospacelab is imported lazily here (never at catalog/codegen import time), after
``bootstrap.seed_geospacelab_config()`` has set the Agg backend and resolved config.
"""

from __future__ import annotations

import contextlib
import io
import logging
import threading
from dataclasses import dataclass

from . import settings
from .capabilities import aacgm_available, apex_available
from .catalog.models import DATAHUB, EXPRESS, GEOMAP
from .catalog.registry import express_class_for
from .codegen import (
    _layout_groups,
    _selected_or_default,
    build_dock_kwargs,
    build_express_kwargs,
)
from .credentials import credentials_present
from .errors import credential_message, friendly_error
from .spec import RunRequest

# geospacelab + matplotlib carry global state; serialise actual runs.
_RUN_LOCK = threading.Lock()


@dataclass
class RunResult:
    fig: object | None = None
    data_repr: str = ""
    error: str | None = None
    log: str = ""


def _tail(text: str, limit: int = 20000) -> str:
    return text if len(text) <= limit else "…(truncated)…\n" + text[-limit:]


@contextlib.contextmanager
def _capture_logs():
    """Capture geospacelab's logging + stdout/stderr (it prints a lot) into a buffer.

    Process-global redirection, but runs hold ``_RUN_LOCK`` so only one is active and the
    server is single-session in practice.
    """
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root = logging.getLogger()
    prev_level = root.level
    root.addHandler(handler)
    if prev_level == logging.NOTSET or prev_level > logging.INFO:
        root.setLevel(logging.INFO)
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            yield buf
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)


def _precheck(req: RunRequest, catalog) -> str | None:
    """Return an error string if the request must not run; otherwise None."""
    span = req.span_hours
    if span <= 0:
        return "The end time must be after the start time."
    for spec in req.datasets:
        product = catalog.get(spec.dataset_id)
        if span > product.max_span_hours:
            return (
                f"Time range {span:.0f} h exceeds the {product.max_span_hours:.0f} h preview limit "
                f"for {product.label}. Shorten it or run the generated code locally."
            )
        if product.loader == GEOMAP and not settings.ENABLE_GEOMAP_PREVIEW:
            return (
                f"Live preview is deferred for {product.label} (needs cartopy and a manual file). "
                "The generated code is ready to copy."
            )
        if settings.is_docker() and product.credential is not None:
            return (
                f"Live preview is disabled in this deployment for the credential-gated source "
                f"{product.label}. The generated code is ready to copy."
            )
        if not credentials_present(product.credential):
            return credential_message(product.credential, product.label)
        if spec.params.get("add_APEX") and not apex_available():
            return (
                "“Add APEX magnetic coords” needs the apexpy package, which isn't installed. "
                "Install it with `pip install 'gsl-dashboard[apex]'` (requires a Fortran compiler), "
                "or turn the option off. The generated code is still ready to copy."
            )
        if spec.params.get("add_AACGM") and not aacgm_available():
            return (
                "“Add AACGM magnetic coords” needs the aacgmv2 package, which isn't installed. "
                "Install it (`pip install aacgmv2`) or turn the option off. "
                "The generated code is still ready to copy."
            )
    return None


def build_and_render(req: RunRequest, catalog) -> RunResult:
    if not req.datasets:
        return RunResult(error="Select a dataset first.")
    err = _precheck(req, catalog)
    if err:
        return RunResult(error=err)

    with _RUN_LOCK:
        import matplotlib

        matplotlib.use("Agg")
        from .bootstrap import prime_in_memory_config

        prime_in_memory_config()
        with _capture_logs() as buf:
            try:
                single = req.is_single and catalog.get(req.datasets[0].dataset_id).loader == EXPRESS
                result = _run_express(req, catalog) if single else _run_datahub(req, catalog)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                result = RunResult(error=friendly_error(exc))
        result.log = _tail(buf.getvalue())
        return result


def _figure_of(dash):
    return getattr(dash, "figure", None) or getattr(dash, "fig", None)


def _run_express(req: RunRequest, catalog) -> RunResult:
    spec = req.datasets[0]
    product = catalog.get(spec.dataset_id)
    cls = express_class_for(product)
    kwargs = build_express_kwargs(product, spec.params)
    dash = cls(req.dt_fr, req.dt_to, **kwargs)
    dash.quicklook()
    return RunResult(fig=_figure_of(dash), data_repr=_summary_from_dashboard(dash))


def _run_datahub(req: RunRequest, catalog) -> RunResult:
    from geospacelab.visualization.mpl.dashboards import TSDashboard

    db = TSDashboard(dt_fr=req.dt_fr, dt_to=req.dt_to, figure_config={"figsize": (12, 8)})
    panels = []
    summary_rows = []
    for spec in req.datasets:
        product = catalog.get(spec.dataset_id)
        if product.loader != DATAHUB:
            continue
        ds = db.dock(datasource_contents=list(product.datasource_contents), **build_dock_kwargs(product, spec.params))
        for group in _layout_groups(product, _selected_or_default(product, spec)):
            refs = []
            for name in group:
                var = db.assign_variable(name, dataset=ds)
                refs.append(var)
                summary_rows.append(_describe_var(name, var))
            panels.append(refs)
    if not panels:
        return RunResult(error="No variables selected to plot.")
    db.set_layout(panel_layouts=panels)
    db.draw()
    if req.title:
        db.add_title(title=req.title)
    return RunResult(fig=_figure_of(db), data_repr=_rows_to_markdown(summary_rows))


# --- data summary helpers (best-effort; never fail the run) -----------------------

def _describe_var(name: str, var) -> tuple[str, str, str]:
    shape = unit = "?"
    try:
        value = getattr(var, "value", None)
        shape = str(getattr(value, "shape", "")) or "scalar"
        unit = str(getattr(var, "unit", "") or "")
    except Exception:
        pass
    return name, shape, unit


def _rows_to_markdown(rows) -> str:
    if not rows:
        return ""
    out = ["| variable | shape | unit |", "| --- | --- | --- |"]
    for name, shape, unit in rows:
        out.append(f"| {name} | {shape} | {unit} |")
    return "\n".join(out)


def _summary_from_dashboard(dash) -> str:
    try:
        rows = []
        for ds in getattr(dash, "datasets", {}).values():
            label = getattr(ds, "label", lambda: "dataset")()
            rows.append(f"- {label}")
        return "Docked datasets:\n" + "\n".join(rows) if rows else ""
    except Exception:
        return ""
