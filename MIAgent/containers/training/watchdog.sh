#!/bin/sh
set -eu

# Compose health checks report health but do not restart unhealthy containers.
# Exit after four consecutive failures so restart: unless-stopped takes effect.
failures=0
while true; do
    sleep 150 &
    wait "$!"
    if timeout 15s nvidia-smi -L >/dev/null 2>&1; then
        failures=0
        continue
    fi
    failures=$((failures + 1))
    echo "training-watchdog: nvidia-smi failed (${failures}/4)" >&2
    if [ "$failures" -ge 4 ]; then
        echo "training-watchdog: exiting so Docker restarts training" >&2
        exit 1
    fi
done
