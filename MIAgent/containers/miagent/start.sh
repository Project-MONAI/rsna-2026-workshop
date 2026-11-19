#!/bin/sh
set -eu

settings_dir="${HOME}/.local/share/code-server/User"
settings_file="${settings_dir}/settings.json"

mkdir -p "${settings_dir}"
if [ ! -e "${settings_file}" ]; then
    cp /etc/miagent/code-server-settings.json "${settings_file}"
fi

python3 /usr/local/bin/miagent-markdown-settings

exec supervisord -c /etc/miagent/supervisord.conf
