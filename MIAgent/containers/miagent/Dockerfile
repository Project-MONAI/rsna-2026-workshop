FROM docker:28-cli AS docker-cli

FROM codercom/code-server:latest

ARG LOCAL_UID=1000
ARG LOCAL_GID=1000
ARG NIIVUE_VERSION=2.5.7
ARG OPENCODE_VERSION=1.18.30

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git python3 python3-yaml supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose

RUN curl -fsSL \
       "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-x64.tar.gz" \
       | tar -xz -C /usr/local/bin \
    && curl -fsSL \
       "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/KorbinianEckstein/vsextensions/niivue/${NIIVUE_VERSION}/vspackage" \
       -o /tmp/niivue.vsix.gz \
    && gzip -dc /tmp/niivue.vsix.gz > /tmp/niivue.vsix \
    && code-server --extensions-dir /usr/local/share/code-server/extensions --install-extension /tmp/niivue.vsix \
    && rm -f /tmp/niivue.vsix /tmp/niivue.vsix.gz

RUN if ! getent group "${LOCAL_GID}" >/dev/null; then groupadd --gid "${LOCAL_GID}" miagent; fi \
    && if ! getent passwd "${LOCAL_UID}" >/dev/null; then \
         useradd --uid "${LOCAL_UID}" --gid "${LOCAL_GID}" --create-home --shell /bin/bash miagent; \
       fi \
    && mkdir -p /miagent-home /usr/local/share/code-server/extensions \
    && chown "${LOCAL_UID}:${LOCAL_GID}" /miagent-home \
    && chown -R "${LOCAL_UID}:${LOCAL_GID}" /usr/local/share/code-server

WORKDIR /workspace

COPY . /opt/miagent-seed/
COPY containers/lab/init.py /usr/local/bin/miagent-lab-init
COPY containers/miagent/start.sh /usr/local/bin/miagent-start
COPY containers/miagent/ll /usr/local/bin/ll
RUN chmod 0755 /usr/local/bin/ll
COPY containers/miagent/supervisord.conf /etc/miagent/supervisord.conf
COPY containers/miagent/code-server-settings.json /etc/miagent/code-server-settings.json
COPY containers/miagent/configure_markdown_preview.py /usr/local/bin/miagent-markdown-settings
COPY containers/archive-tracking/start.sh /usr/local/bin/archive-tracking-start
RUN mkdir -p /var/lib/miagent-lab
