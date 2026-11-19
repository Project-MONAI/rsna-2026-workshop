FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY containers/tracking/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/requirements.lock \
    && python -m pip check \
    && rm -f /tmp/requirements.lock

WORKDIR /workspace

COPY containers/tracking/supervisord.conf /etc/miagent/supervisord.conf
COPY containers/archive-tracking/start.sh /usr/local/bin/archive-tracking-start
COPY containers/archive-tracking/supervisord.conf /etc/miagent/archive-tracking-supervisord.conf
