FROM kalilinux/kali-rolling

# Base Kali + core agent runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Curated CyberLab Tool Arsenal -- a deliberate selection, not a Kali
# package dump (see docs/tools.md for the full audit and rationale behind
# every inclusion/exclusion). Installed in layered groups matching the Tool
# Registry categories so a rebuild after adding one tool only invalidates
# that layer, and so `docker history` reads as documentation.

# Network / host reconnaissance.
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    masscan \
    arp-scan \
    netdiscover \
    && rm -rf /var/lib/apt/lists/*

# DNS / network utilities.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bind9-dnsutils \
    traceroute \
    whois \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Web reconnaissance + web security scanning. dirb is installed only for
# its bundled small wordlists (/usr/share/wordlists/dirb/common.txt) that
# gobuster/ffuf need for directory enumeration -- not registered as a tool
# itself (nikto already covers dirb's own scanning use case).
RUN apt-get update && apt-get install -y --no-install-recommends \
    whatweb \
    nikto \
    wafw00f \
    gobuster \
    ffuf \
    nuclei \
    sqlmap \
    dirb \
    && rm -rf /var/lib/apt/lists/*

# SSL/TLS auditing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    sslscan \
    testssl.sh \
    && rm -rf /var/lib/apt/lists/*

# Enumeration (SMB/LDAP) + vulnerability/exploit-DB lookup.
RUN apt-get update && apt-get install -y --no-install-recommends \
    enum4linux \
    smbclient \
    samba-common-bin \
    ldap-utils \
    exploitdb \
    lynis \
    && rm -rf /var/lib/apt/lists/*

# OSINT.
RUN apt-get update && apt-get install -y --no-install-recommends \
    theharvester \
    amass \
    subfinder \
    dnsrecon \
    && rm -rf /var/lib/apt/lists/*

# General-purpose utilities.
RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Deliberately NOT installed: hydra/john/hashcat. Both exist in Kali's repos
# and were considered, but neither fits the target_id-centric Job Engine
# model cleanly -- john/hashcat operate on offline hash files, not a scan
# target, and hydra is genuine brute-force amplification risk even against a
# LAB target. Documented as a deferred decision in docs/tools.md, not a
# silent omission.

WORKDIR /agent
COPY agent/requirements.txt .
# --ignore-installed: theharvester (it ships its own FastAPI/uvicorn-based
# REST mode) pulls in a Debian-packaged uvicorn as an apt dependency, which
# pip then refuses to touch ("no RECORD file") since dpkg, not pip, owns it.
# This installs our pinned versions alongside/over it rather than erroring.
RUN pip install --no-cache-dir --break-system-packages --ignore-installed -r requirements.txt

COPY agent/main.py .

RUN useradd -m -u 1000 cyberlab
USER cyberlab

EXPOSE 9000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
