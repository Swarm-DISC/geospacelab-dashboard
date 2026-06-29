# GeospaceLAB Dashboard — container image (restricted "docker" runtime).
#
# In docker mode the app points geospacelab's data root at a temp directory and disables
# live previews for credential-gated sources (code generation still works). See entrypoint.sh.
FROM python:3.12-slim-bookworm

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# cartopy needs PROJ/GEOS headers at build time; apexpy (optional) needs gfortran.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libproj-dev proj-data proj-bin libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY app.py ./

# Install the project (add --extra madrigal/vires/geo/apex as needed).
RUN uv pip install --system .

ENV DASHBOARD_MODE=docker \
    PORT=5006 \
    GSL_PREVIEW_TIMEOUT=180

EXPOSE 5006
ENTRYPOINT ["deploy/entrypoint.sh"]
CMD ["panel", "serve", "app.py", "--address", "0.0.0.0", "--port", "5006", "--allow-websocket-origin=*"]
