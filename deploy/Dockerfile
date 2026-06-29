# GeospaceLAB Dashboard — container image (restricted "docker" runtime).
#
# Installs from uv.lock for reproducibility. aacgmv2 and apexpy are deliberately skipped:
# neither ships a wheel, so installing them would need a C/Fortran compiler. geospacelab
# imports both lazily, and the app degrades gracefully — the AACGM/APEX coordinate toggles
# just show an "install it" message; everything else works.
#
# In docker mode the app points geospacelab's data root at a temp dir and disables live
# previews for credential-gated sources (code generation still works). See entrypoint.sh.
FROM python:3.12-slim-bookworm

# uv for fast, reproducible, lock-based installs. Pinned: `--no-install-package` (used
# below) needs uv >= 0.10, and an unpinned `latest` can resolve to a stale cached image.
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/

# Runtime libs for cartopy (PROJ/GEOS). No compilers — everything else installs from wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libproj-dev libgeos-dev proj-data \
    && rm -rf /var/lib/apt/lists/*

ENV UV_PYTHON_PREFERENCE=only-system \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
COPY src ./src
COPY app.py ./
COPY deploy ./deploy

# Install exactly what's locked, minus the two packages that would require a compiler.
RUN uv sync --locked --no-dev \
        --no-install-package aacgmv2 \
        --no-install-package apexpy \
    && chmod +x deploy/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    DASHBOARD_MODE=docker \
    PORT=5006 \
    GSL_PREVIEW_TIMEOUT=180

EXPOSE 5006
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["panel", "serve", "app.py", "--address", "0.0.0.0", "--port", "5006", "--allow-websocket-origin=*"]
