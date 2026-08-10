FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py docker_manager.py registry.py schema.py ./
COPY definitions ./definitions

# No longer needs root: it no longer mounts /var/run/docker.sock directly,
# it talks to cyberlab-docker-proxy over TCP instead (see docker-compose.yml).
RUN useradd -m -u 1000 labmanager && chown -R labmanager:labmanager /app
USER labmanager

EXPOSE 9100

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9100/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9100"]
