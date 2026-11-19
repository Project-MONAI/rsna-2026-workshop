FROM miagent-core:0.1.0

COPY skills/segmentation/synthseg/requirements.lock /tmp/synthseg-requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/synthseg-requirements.lock \
    && python -m pip check \
    && rm -f /tmp/synthseg-requirements.lock

WORKDIR /workspace
