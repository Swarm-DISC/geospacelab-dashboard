#!/usr/bin/env bash
# Container entrypoint: seed geospacelab credentials from env (optional), then serve.
#
# In docker mode the app (bootstrap.py) writes ~/.geospacelab/config.toml with the data
# root pointed at a temp directory, and the runner refuses live previews for credentialed
# sources. Credentials below are only useful if you flip those sources back on.
set -euo pipefail

CONFIG_DIR="${HOME}/.geospacelab"
CONFIG="${CONFIG_DIR}/config.toml"
mkdir -p "${CONFIG_DIR}"

# Minimal config seed (bootstrap.py overrides data_root_dir with a temp dir at startup).
{
  echo 'package_name = "geospacelab"'
  echo ''
  echo '[datahub]'
  echo 'data_root_dir = ""'
  if [[ -n "${ESA_EO_USERNAME:-}" ]]; then
    echo ''
    echo '[datahub.esa_eo]'
    echo "username = \"${ESA_EO_USERNAME}\""
  fi
  if [[ -n "${MADRIGAL_FULLNAME:-}" ]]; then
    echo ''
    echo '[datahub.madrigal]'
    echo "user_fullname = \"${MADRIGAL_FULLNAME}\""
    echo "user_email = \"${MADRIGAL_EMAIL:-}\""
    echo "user_affiliation = \"${MADRIGAL_AFFILIATION:-}\""
  fi
  if [[ -n "${GSL_WDC_EMAIL:-}" ]]; then
    echo ''
    echo '[datahub.wdc]'
    echo "user_email = \"${GSL_WDC_EMAIL}\""
  fi
} > "${CONFIG}"

# VirES token (optional), only if a SWARM source is set to the VirES backend.
if [[ -n "${VIRES_TOKEN:-}" ]]; then
  viresclient set_token https://vires.services/ows "${VIRES_TOKEN}" || true
  viresclient set_default_server https://vires.services/ows || true
fi

exec "$@"
