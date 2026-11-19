#!/bin/sh
set -eu

mkdir -p /tmp/archive-mlflow /tmp/archive-tracking-logs
cp /archive/tracking/mlflow/metadata.db /tmp/archive-mlflow/metadata.db

exec supervisord -c /etc/miagent/archive-tracking-supervisord.conf
