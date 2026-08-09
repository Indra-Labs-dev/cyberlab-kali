FROM kalilinux/kali-rolling

RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    whatweb \
    nikto \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /agent
COPY agent/requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY agent/main.py .

RUN useradd -m -u 1000 cyberlab
USER cyberlab

EXPOSE 9000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
