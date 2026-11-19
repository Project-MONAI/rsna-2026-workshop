#!/bin/sh
set -eu
python3 /usr/local/bin/miagent-paseo-settings
python3 /usr/local/bin/miagent-paseo-terminal
export PASEO_WEB_UI_DIST_DIR="${PASEO_HOME}/miagent-web-ui"
node /usr/local/bin/miagent-paseo-workspace.mjs
exec /usr/local/bin/paseo-docker-entrypoint "$@"
