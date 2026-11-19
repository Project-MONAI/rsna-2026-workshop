FROM core_image

# One persistent scientific environment contains the additive nnUNet and
# SynthSeg dependencies. Keep the validated core pins during this topology change.
COPY containers/nnunet/requirements.lock /tmp/nnunet-requirements.lock
COPY skills/segmentation/synthseg/requirements.lock /tmp/synthseg-requirements.lock
COPY skills/segmentation/nv-segment-ct-finetune/requirements.training-addon.lock /tmp/nv-segment-ct-finetune-requirements.lock
RUN python -m pip install --no-cache-dir \
        -r /tmp/nnunet-requirements.lock \
        -r /tmp/synthseg-requirements.lock \
        -r /tmp/nv-segment-ct-finetune-requirements.lock \
    && python -m pip check \
    && rm -f \
        /tmp/nnunet-requirements.lock \
        /tmp/synthseg-requirements.lock \
        /tmp/nv-segment-ct-finetune-requirements.lock

COPY containers/training/watchdog.sh /usr/local/bin/training-watchdog
RUN chmod 0755 /usr/local/bin/training-watchdog

ENV PYTHONPATH=/runtime/upstreams/nnUNet
WORKDIR /workspace
