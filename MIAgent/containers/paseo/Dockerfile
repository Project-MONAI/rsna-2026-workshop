FROM docker:28-cli AS docker-cli

FROM ghcr.io/getpaseo/paseo:0.9.2

ARG TARGETARCH
ARG OPENCODE_VERSION=1.18.30

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-yaml \
    && rm -rf /var/lib/apt/lists/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose

RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) opencode_arch=x64 ;; \
      arm64) opencode_arch=arm64 ;; \
      *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL \
      "https://github.com/anomalyco/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${opencode_arch}.tar.gz" \
      | tar -xz -C /usr/local/bin; \
    opencode --version

COPY containers/paseo/configure_local_provider.py /usr/local/bin/miagent-paseo-settings
COPY containers/paseo/start.sh /usr/local/bin/miagent-paseo-start
COPY containers/paseo/configure_workspace.mjs /usr/local/bin/miagent-paseo-workspace.mjs
COPY containers/paseo/configure_terminal.py /usr/local/bin/miagent-paseo-terminal
COPY containers/paseo/patch_file_tabs.py /usr/local/bin/miagent-paseo-file-tabs
RUN python3 /usr/local/bin/miagent-paseo-file-tabs /usr/local/lib/node_modules/@getpaseo/server
COPY containers/miagent/ll /usr/local/bin/ll
RUN chmod 0755 /usr/local/bin/miagent-paseo-start
RUN chmod 0755 /usr/local/bin/ll

ENV SHELL=/bin/bash

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/miagent-paseo-start"]
