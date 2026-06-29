"""Sidebar input widgets: the dropdown directory, per-product params, time, datasets."""

from __future__ import annotations

import panel as pn

from ..catalog.models import DATAHUB


# --- cascading dropdown directory ---
def cascade_widgets(state):
    return (
        pn.widgets.Select.from_param(state.param.category, name="Category"),
        pn.widgets.Select.from_param(state.param.source_group, name="Source"),
        pn.widgets.Select.from_param(state.param.product, name="Product"),
    )


def _widget_for(state, spec):
    label = spec.label or spec.name
    p = state.param[spec.name]
    if spec.widget == "bool":
        return pn.widgets.Checkbox.from_param(p, name=label)
    if spec.widget == "text":
        return pn.widgets.TextInput.from_param(p, name=label)
    return pn.widgets.Select.from_param(p, name=label)


def param_box(state):
    def _build(_product_id):
        widgets = [_widget_for(state, sp) for sp in state.active_product.params]
        if not widgets:
            return pn.pane.Markdown("_This product has no extra parameters._", styles={"font-size": "12px"})
        return pn.Column(*widgets)

    return pn.bind(_build, state.param.product)


def variables_box(state):
    def _build(_product_id):
        product = state.active_product
        if product.loader != DATAHUB or not product.variables:
            return pn.Column()
        return pn.widgets.MultiSelect.from_param(
            state.param.variables, name="Variables (one panel each / grouped)", size=8
        )

    return pn.bind(_build, state.param.product)


def note_box(state):
    def _build(_product_id):
        note = state.active_product.note
        return pn.pane.Alert(note, alert_type="info", styles={"font-size": "12px"}) if note else pn.Column()

    return pn.bind(_build, state.param.product)


def time_widgets(state):
    return (
        pn.widgets.DatetimePicker.from_param(state.param.dt_fr, name="Start (UTC)"),
        pn.widgets.DatetimePicker.from_param(state.param.dt_to, name="End (UTC)"),
    )


def datasets_box(state):
    def _build(datasets):
        if not datasets:
            return pn.pane.Markdown(
                '_No added datasets — the current selection is plotted. Use **Add dataset** to combine several._',
                styles={"font-size": "12px"},
            )
        rows = []
        for i, spec in enumerate(datasets):
            label = state.catalog.get(spec.dataset_id).label
            btn = pn.widgets.Button(name="✕", width=34, button_type="light")
            btn.on_click(lambda _e, idx=i: state.remove_dataset(idx))
            rows.append(
                pn.Row(pn.pane.Markdown(f"**{i + 1}.** {label}", sizing_mode="stretch_width"), btn)
            )
        clear = pn.widgets.Button(name="Clear all", button_type="light", width=90)
        clear.on_click(state.clear_datasets)
        rows.append(clear)
        return pn.Column(*rows)

    return pn.bind(_build, state.param.datasets)


def add_button(state):
    btn = pn.widgets.Button(name="➕ Add dataset to plot", button_type="default", sizing_mode="stretch_width")
    btn.on_click(state.add_dataset)
    return btn


def run_controls(state):
    run = pn.widgets.Button(name="▶ Run preview", button_type="primary", sizing_mode="stretch_width", height=42)
    run.on_click(state.run_preview)
    stop = pn.widgets.Button(name="■ Stop", button_type="danger", width=90, height=42, disabled=True)
    stop.on_click(state.stop_preview)

    def _on_running(e):
        run.loading = e.new
        stop.disabled = not e.new

    state.param.watch(_on_running, "is_running")
    return pn.Row(run, stop, sizing_mode="stretch_width")


def sidebar(state) -> pn.viewable.Viewable:
    cat, grp, prod = cascade_widgets(state)
    fr, to = time_widgets(state)
    return pn.Column(
        pn.pane.Markdown("### 1 · Choose a dataset"),
        cat, grp, prod,
        note_box(state),
        pn.layout.Divider(),
        pn.pane.Markdown("### 2 · Parameters"),
        param_box(state),
        variables_box(state),
        pn.layout.Divider(),
        pn.pane.Markdown("### 3 · Time range"),
        fr, to,
        pn.layout.Divider(),
        pn.pane.Markdown("### 4 · Combine (optional)"),
        add_button(state),
        datasets_box(state),
        pn.layout.Divider(),
        run_controls(state),
        sizing_mode="stretch_width",
    )
