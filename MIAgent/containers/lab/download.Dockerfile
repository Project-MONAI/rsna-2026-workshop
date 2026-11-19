FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
RUN python -m pip install --no-cache-dir huggingface-hub==0.36.0
COPY containers/lab/download_model.py /opt/download_model.py
ENTRYPOINT ["python3", "/opt/download_model.py"]
