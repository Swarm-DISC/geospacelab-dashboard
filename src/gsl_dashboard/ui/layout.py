"""Assemble the FastListTemplate: sidebar inputs + tabbed outputs + bookmarks."""

from __future__ import annotations

import panel as pn

from .. import settings
from ..bookmarks import all_bookmarks, apply_bookmark, save_user_bookmark
from ..state import RequestState
from . import panes, widgets

ACCENT = "#1565c0"


def _bookmark_card(state, bm, sidebar_tabs) -> pn.viewable.Viewable:
    load = pn.widgets.Button(name="Load", button_type="primary", width=80)

    def _load(_e, bookmark=bm):
        apply_bookmark(bookmark, state)
        sidebar_tabs.active = 0  # flip back to the "Choose dataset" tab so params are visible
        if pn.state.notifications:
            pn.state.notifications.info(f"Loaded “{bookmark.name}”. Click Run to preview.")

    load.on_click(_load)
    tag = "" if bm.builtin else "  ·  _saved_"
    return pn.Column(
        pn.pane.Markdown(f"**{bm.name}**{tag}"),
        pn.pane.Markdown(bm.description or "", styles={"font-size": "12px", "color": "#555"}),
        load,
        styles={"border": "1px solid #e0e0e0", "border-radius": "8px", "padding": "12px", "background": "#fafafa"},
        width=330,
        margin=6,
    )


def _bookmarks_view(state, sidebar_tabs) -> pn.viewable.Viewable:
    container = pn.FlexBox(sizing_mode="stretch_width")

    def rebuild():
        container.objects = [_bookmark_card(state, bm, sidebar_tabs) for bm in all_bookmarks()]

    save_name = pn.widgets.TextInput(placeholder="Name this view…", width=260)
    save_btn = pn.widgets.Button(name="💾 Save current", button_type="success")

    def _save(_e):
        name = (save_name.value or "").strip()
        if not name:
            return
        save_user_bookmark(name, state.current_request())
        save_name.value = ""
        rebuild()
        if pn.state.notifications:
            pn.state.notifications.success(f"Saved bookmark “{name}”.")

    save_btn.on_click(_save)
    rebuild()
    return pn.Column(
        pn.pane.Markdown("### Bookmarks — one-click presets"),
        pn.pane.Markdown(
            "Load a preset into the editor (then Run to preview), or save the current selection.",
            styles={"font-size": "12px", "color": "#555"},
        ),
        pn.Row(save_name, save_btn),
        pn.layout.Divider(),
        container,
        sizing_mode="stretch_width",
    )


def build_app() -> pn.template.FastListTemplate:
    pn.extension("codeeditor", notifications=True, sizing_mode="stretch_width")

    state = RequestState()

    # Top half: the generated code, always visible. Bottom half: Plot / Data / Console tabs.
    code_half = pn.Column(
        pn.pane.Markdown("##### Generated geospacelab code", margin=(2, 0, 0, 6)),
        panes.code_pane(state),
        sizing_mode="stretch_both",
        styles={"flex": "1 1 0", "min-height": "0"},
    )
    output_half = pn.Column(
        pn.Tabs(
            ("Plot", pn.Column(panes.plot_pane(state), sizing_mode="stretch_both")),
            ("Data", pn.Column(panes.data_pane(state), sizing_mode="stretch_both")),
            ("Console", pn.Column(panes.console_pane(state), sizing_mode="stretch_both")),
            sizing_mode="stretch_both",
        ),
        sizing_mode="stretch_both",
        styles={"flex": "1 1 0", "min-height": "0"},
    )
    # Run controls sit between the generated code (top) and the output tabs (bottom).
    main_view = pn.Column(code_half, widgets.run_controls(state), output_half, sizing_mode="stretch_both")

    # Left panel: two tabs — "Choose dataset" (the input directory) and "Bookmarks".
    sidebar_tabs = pn.Tabs(sizing_mode="stretch_width")
    sidebar_tabs.extend([
        ("Choose dataset", widgets.sidebar(state)),
        ("Bookmarks", _bookmarks_view(state, sidebar_tabs)),
    ])

    mode_badge = pn.pane.HTML(
        f"<span style='font-size:12px;color:#888'>mode: <b>{settings.MODE}</b></span>",
        styles={"margin-top": "6px"},
    )

    return pn.template.FastListTemplate(
        title="GeospaceLAB Dashboard",
        header=[pn.Row(panes.credential_status_bar(), mode_badge)],
        sidebar=[sidebar_tabs],
        main=[main_view],
        sidebar_width=400,
        accent=ACCENT,
        theme_toggle=False,
    )
