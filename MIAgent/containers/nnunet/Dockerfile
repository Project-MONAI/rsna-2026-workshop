FROM miagent-core:0.1.0

COPY containers/nnunet/requirements.lock /tmp/nnunet-requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/nnunet-requirements.lock \
    && python -m pip check \
    && rm -f /tmp/nnunet-requirements.lock

ENV PYTHONPATH=/runtime/upstreams/nnUNet
WORKDIR /workspace
