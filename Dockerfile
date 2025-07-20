# optimiser/Dockerfile  – single stage, multi-arch friendly
FROM python:3.10-slim-bookworm
FROM python:3.10-slim-bookworm

# ---- system deps required to compile C extensions ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY optimiser/requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# 2) copy code
COPY optimiser/ ./optimiser
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "optimiser"]

