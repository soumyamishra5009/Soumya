# SyncForge AI — API image for cloud/container hosts (Render, Fly, Railway, Docker).
#
# Uses the lean requirements-cloud.txt (no local Whisper / Celery) and installs
# git so the offline "Ship It" provider works inside the container.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git powers the local Ship It provider. --no-install-recommends keeps it small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-cloud.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Render/Fly/Railway inject $PORT; fall back to 8000 for a plain `docker run`.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
