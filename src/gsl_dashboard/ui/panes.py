"""Output panes: generated code, plot preview, data summary, credential status."""

from __future__ import annotations

import html

import panel as pn

from ..credentials import status as cred_status

_PLOT_PLACEHOLDER = (
    "### Plot preview\n\nConfigure a dataset and click **▶ Run preview**. "
    "geospacelab downloads real data, so the first run for a time range may take a moment."
)


def code_pane(state) -> pn.widgets.CodeEditor:
    editor = pn.widgets.CodeEditor(
        value=state.code,
        language="python",
        readonly=True,
        theme="github",
        sizing_mode="stretch_both",
        min_height=220,
    )
    state.param.watch(lambda e: setattr(editor, "value", e.new), "code")
    return editor


def plot_pane(state) -> pn.viewable.Viewable:
    def _view(png, running, error):
        if running:
            return pn.Column(
                pn.indicators.LoadingSpinner(value=True, size=40, name="Running…"),
                pn.pane.Markdown("Downloading data and rendering…"),
            )
        if error:
            return pn.pane.Alert(f"**Preview unavailable.** {error}", alert_type="warning")
        if not png:
            return pn.pane.Markdown(_PLOT_PLACEHOLDER)
        # PNG bytes rendered out-of-process (see state.run_preview / preview_worker).
        return pn.pane.PNG(png, sizing_mode="stretch_both", min_height=420)

    return pn.bind(_view, state.param.preview_png, state.param.is_running, state.param.error_msg)


def data_pane(state) -> pn.viewable.Viewable:
    def _view(data_repr, png):
        if data_repr:
            return pn.pane.Markdown(data_repr, sizing_mode="stretch_width")
        if png:
            return pn.pane.Markdown("_Preview rendered; no tabular summary available for this product._")
        return pn.pane.Markdown("_Run a preview to see a data summary._")

    return pn.bind(_view, state.param.data_repr, state.param.preview_png)


def console_pane(state) -> pn.viewable.Viewable:
    """Non-interactive log console: shows geospacelab's output from the last run."""

    def _view(log, running):
        text = log or ("Running… logs will stream here when the run finishes." if running
                       else "Logs from the last preview run appear here (geospacelab output, warnings, errors).")
        return pn.pane.HTML(
            "<pre style='white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,"
            "Menlo,Consolas,monospace;font-size:12px;line-height:1.4;max-height:560px;overflow:auto;"
            "background:#0f1419;color:#d6deeb;padding:12px;border-radius:6px;margin:0'>"
            f"{html.escape(text)}</pre>",
            sizing_mode="stretch_both",
        )

    return pn.bind(_view, state.param.console_log, state.param.is_running)


def credential_status_bar() -> pn.viewable.Viewable:
    st = cred_status()
    dots = []
    labels = {"esa_eo": "ESA-EO", "madrigal": "Madrigal", "vires": "VirES"}
    for kind, ok in st.items():
        colour = "#2e9e44" if ok else "#b0b0b0"
        mark = "●" if ok else "○"
        dots.append(
            f"<span style='color:{colour};font-size:13px' title='{labels[kind]} credentials "
            f"{'configured' if ok else 'not configured'}'>{mark} {labels[kind]}</span>"
        )
    return pn.pane.HTML("&nbsp;&nbsp;".join(dots), styles={"margin-top": "6px"})
