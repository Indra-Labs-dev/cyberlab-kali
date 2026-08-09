# Changelog

## Unreleased — Phase 2 — Kali container + worker pipeline

- Conteneur `cyberlab-kali` (`kalilinux/kali-rolling` + nmap/whatweb/nikto) exposant un agent FastAPI interne (`kali/agent/main.py`) sur le réseau isolé `cyberlab-kali-net` uniquement (aucun port publié sur l'hôte).
- Agent : allowlist stricte des exécutables résolue au démarrage, `subprocess.run(..., shell=False)`, validation des arguments (rejet des métacaractères shell), authentification par secret partagé (`KALI_AGENT_TOKEN`), timeout plafonné à 300s. Tests unitaires (`kali/agent/tests/`).
- Durcissement conteneur : `cap_drop: ALL`, `no-new-privileges`, utilisateur non-root, sans accès à `docker.sock`.
- `cyberlab-worker` : worker RQ (`backend/app/jobs/worker.py`) consommant la file Redis `default`, exécutant les tâches (`backend/app/jobs/tasks.py`) qui délèguent à l'agent Kali via `backend/app/jobs/kali_client.py`.
- Pipeline vérifié de bout en bout : FastAPI → Redis (RQ) → Worker → Agent Kali → `nmap` → résultat récupéré via `job.result`.
- Constat documenté (`docs/security.md`) : `cap_drop: ALL` bloque les scans nmap nécessitant `CAP_NET_RAW` (ex. `-sS`) — utiliser `-sT` par défaut.

## Unreleased — Phase 1 — Foundation

- Initialisation du dépôt git.
- Squelette backend FastAPI (`backend/`) : config via `pydantic-settings`, session SQLAlchemy async, endpoints `/api/health` et `/api/health/db`, Alembic prêt (pas encore de modèles).
- Squelette frontend Nuxt 4 (`frontend/`) : Tailwind CSS, page d'accueil vérifiant l'état API/DB.
- `docker-compose.yml` : services `cyberlab-frontend`, `cyberlab-api`, `cyberlab-postgres`, `cyberlab-redis`, réseaux séparés (`cyberlab-backend`, `cyberlab-kali-net` réservé pour la Phase 2), volumes persistants, healthchecks, limites mémoire/CPU.
- Ports hôte remappés (3300/8300/55432/63790) pour éviter les conflits avec une stack Docker locale déjà active (`indralabs-*`).
- `.env.example` avec toutes les variables nécessaires.
