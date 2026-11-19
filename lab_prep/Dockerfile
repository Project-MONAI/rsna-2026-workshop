FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/tmp

WORKDIR /opt/lab-prep
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY prepare.py test_prepare.py ./

USER 1000:1000
ENTRYPOINT ["python", "/opt/lab-prep/prepare.py"]
