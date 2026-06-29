# GeospaceLAB Dashboard

A web dashboard that turns [geospacelab](https://github.com/JouleCai/geospacelab) into a
point-and-click explorer. Build a data request through a **directory of dropdowns**, watch
the equivalent **geospacelab Python code generated live**, and render a **quick plot
preview** on demand. A **Bookmarks** tab offers one-click presets (and lets you save your
own). Modelled on the [Swarm-DISC VirES dashboard](https://github.com/Swarm-DISC/dashboards).

```
┌ sidebar ───────────────┐ ┌ main ──────────────────────────────────┐
│ [Choose dataset][⭐ Bookmarks] │  Generated geospacelab code (top half) │
│ 1 · Choose dataset     │ │  import datetime                       │
│   Category ▾           │ │  from geospacelab... import ...        │ ← live
│   Source   ▾           │ │  dashboard = ...; dashboard.quicklook()│
│   Product  ▾           │ ├────────────────────────────────────────┤
│ 2 · Parameters         │ │ [ Plot ] [ Data ] [ Console ]  (bottom) │
│   sat_id, source, ...  │ │                                        │
│ 3 · Time range         │ │  Plot → matplotlib preview after ▶Run  │
│ 4 · Combine (+)        │ │  Console → geospacelab logs            │
│   [▶ Run preview][■Stop]│ │                                        │
└────────────────────────┘ └────────────────────────────────────────┘
```

## Features

- **Tabbed left panel** — **Choose dataset** (cascading Category → Source → Product, then
  per-product params) and **Bookmarks**. Covers OMNI, geomagnetic indices (Kp/Dst/AE/ASY-SYM),
  EISCAT, Millstone Hill, DMSP, the full **Swarm** catalog (~30 products, auto-generated from
  the installed package), and AMPERE/SuperDARN scaffolds.
- **Swarm source & variant toggles** — switch the loading backend (**ESA EO / VirES /
  HAPI**) and **OPER / FAST**; the generated `dock(...)` call updates accordingly
  (`from_VirES` / `from_HAPI` / `from_FAST`). `viresclient` and `hapiclient` are bundled and
  the VirES + HAPI paths are verified end-to-end for Swarm MAG low-rate data.
- **Live code generation** — copy-paste-ready geospacelab code, always in sync with the widgets.
- **On-demand preview** — explicit **Run** button executes geospacelab in a background
  thread and embeds the matplotlib figure; a **Stop** button cancels the wait. Errors inline.
- **Console tab** — a read-only log console showing geospacelab's stdout/stderr/warnings
  from the last run.
- **Multi-dataset plots** — *Add dataset* combines several datahub products into one
  multi-panel `TSDashboard`.
- **Bookmarks** — shipped presets seeded from the geospacelab-swarm examples, plus save-your-own.

## Quickstart (local)

Requires Python ≥ 3.11. We use [uv](https://docs.astral.sh/uv/). The pinned **3.12**
(`.python-version`) matters: Python 3.14 is too new for geospacelab's compiled deps
(cartopy, apexpy, aacgmv2, cdflib), so `uv` reads the file and picks 3.12 automatically.

```bash
uv venv                       # uses Python 3.12 from .python-version
uv pip install -e .            # add extras as needed, e.g. --extra madrigal --extra apex
cp .env.example .env           # optional
uv run panel serve app.py --show
# → http://localhost:5006/app
```

`viresclient` and `hapiclient` are core (the Swarm VirES/HAPI backends). The **`apex`**
extra (`apexpy` — needs a Fortran compiler) enables the Swarm **"Add APEX magnetic coords"**
toggle; without it that toggle previews with a clear "install apexpy" message and the
generated code still works. `aacgmv2` (AACGM coords) ships with geospacelab.

In **local mode** (the default) the app uses your existing `~/.geospacelab/config.toml`
**verbatim** — your data path and credentials are untouched. The recommended first run is
the **OMNI storm** bookmark: it needs no credentials and exercises the whole loop.

## Credentials

Credentials are owned by geospacelab, not this app. Configure them once in
`~/.geospacelab/config.toml`:

| Source | Needs | Config |
| --- | --- | --- |
| OMNI, geomagnetic indices | nothing (WDC asks a contact email — see below) | — |
| Swarm (ESA EO) | ESA Earth-Online account | `[datahub.esa_eo] username = "..."` (password via keyring) |
| Swarm (VirES) | VirES token | `viresclient set_token ...` |
| EISCAT / Millstone / DMSP | Madrigal account | `[datahub.madrigal] user_fullname/user_email/user_affiliation` |

The header shows a status dot per credential. Code generation always works regardless;
only the live preview is gated.

**WDC email:** WDC indices (and OMNI, which uses them) ask for a contact email on first
download. The app injects one into geospacelab's in-memory config (no disk write) so the
server never blocks on stdin — set `GSL_WDC_EMAIL` to control it, otherwise it falls back
to your `esa_eo` username.

## Docker mode

```bash
docker build -f deploy/Dockerfile -t gsl-dashboard .
docker run -p 5006:5006 -e DASHBOARD_MODE=docker gsl-dashboard
```

`DASHBOARD_MODE=docker` makes the app **(a)** point geospacelab's data root at a throwaway
temp directory and **(b)** disable live previews for any credential-gated source (the code
is still generated). `deploy/entrypoint.sh` injects credentials from env vars if you want
to re-enable specific sources.

## Architecture

```
app.py                      seed config (mode-aware) → build_app().servable()
src/gsl_dashboard/
  settings.py               DASHBOARD_MODE + guardrail knobs
  bootstrap.py              Agg backend, MPLCONFIGDIR, mode-aware config, WDC-email priming
  catalog/
    sources_core.yaml       hand-curated non-Swarm sources
    sources_swarm.yaml      AUTO-GENERATED Swarm catalog (scripts/gen_swarm_catalog.py)
    models.py / __init__.py typed catalog + YAML loader (offline, single source of truth)
    registry.py             resolve "module:Class" express targets
  spec.py                   frozen RequestSpec / RunRequest
  codegen.py                pure code generation (express + datahub templates)
  runner.py                 structured builder: guardrails → dock/quicklook → capture figure
  credentials.py / errors.py
  state.py                  param.Parameterized: cascade, live code regen, async Run
  bookmarks/                seeds.yaml + apply/save
  ui/                       panes, sidebar widgets, FastListTemplate layout
```

Design notes:
- The **catalog is the single source of truth** and is fully offline (no geospacelab import),
  so most logic is unit-testable without the heavy stack.
- The preview uses a **structured builder, not `exec()`** of the shown code — it consumes the
  same `RunRequest` and the same param→kwargs translators as codegen, so the previewed plot
  matches the displayed code.
- The Swarm catalog is regenerated from the installed package, not hand-maintained:
  ```bash
  uv run python scripts/gen_swarm_catalog.py
  ```
  It lists only **time-series-plottable** variables — registered in geospacelab's
  `variable_config.py` with a `plot_config.style` *and* a standard `UT` time dependence.
  Two classes are excluded: raw vector arrays (`B_VFM`, `B_NEC`), which the loader splits
  into scalars (`B_VFM_x/y/z`, `B_N/B_E/B_C`) and which crash `db.draw()`; and variables on
  a secondary time grid (e.g. AEJ_LPL's `RMS_MISFIT`/`CONFIDENCE` use `UT_QUAL`), which warn
  "The dependence on UT is not set!".

## Testing

```bash
uv run pytest                 # offline units + install introspection
uv run pytest -m "not install"  # offline only (no geospacelab needed)
```

`test_catalog_introspection.py` checks the catalog against the installed geospacelab
(express class signatures, `TSDashboard` API, the `.figure` attribute, Swarm source paths)
so upstream drift is caught.

## Known limitations

- **AMPERE / SuperDARN** are not express dashboards and need cartopy + a manually downloaded
  file. v1 generates a code scaffold for them; live preview is deferred (enable attempts with
  `GSL_ENABLE_GEOMAP_PREVIEW=1`).
- Swarm `quality_control` is off by default — some products lack the filter method geospacelab
  calls when it is on.
- Previews run one at a time (geospacelab/matplotlib hold global state) and the timeout is
  cosmetic (a runaway download keeps going in the background). Fine for single-user/local;
  revisit before multi-user hosting.
