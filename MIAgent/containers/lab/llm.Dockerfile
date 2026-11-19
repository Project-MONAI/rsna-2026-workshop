ARG VLLM_IMAGE=vllm/vllm-openai:nightly
FROM ${VLLM_IMAGE}
COPY containers/lab/download_model.py /opt/download_model.py
