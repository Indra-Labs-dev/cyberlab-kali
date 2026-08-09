# Changelog

## Unreleased — Phase 4 — Job Engine (persistence + real-time updates)

- Modèle `Job` (`backend/app/models/job.py`) : id, tool, target, params, status (`QUEUED`/`RUNNING`/`SUCCESS`/`FAILED`/`CANCELLED`), timestamps, stdout/stderr/exit_code/result/error. Migration Alembic générée et appliquée.
- `POST /api/jobs` valide via le Tool Registry **avant** toute écriture en base (échec rapide sur outil/paramètres invalides), persiste le job en `QUEUED`, puis l'enfile dans RQ avec le même id.
- `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`.
- `execute_job()` (worker) : transitions de statut persistées en PostgreSQL (session synchrone dédiée, `backend/app/db/sync_session.py`) et diffusées en temps réel via Redis pub/sub (`backend/app/jobs/pubsub.py`).
- `WS /api/ws/jobs/{job_id}` : relaie les mises à jour pub/sub au frontend en temps réel.
- Correction d'une race condition découverte en test : un job annulé pendant son exécution ne peut plus voir son statut `CANCELLED` écrasé par le résultat tardif du worker (`execute_job` revérifie le statut avant chaque écriture terminale).
- Correction d'un bug réel trouvé en testant nikto de bout en bout : `-output -` faisait échouer nikto (tentait d'écrire dans un fichier `-.txt`) — nikto écrit du texte sur stdout par défaut, sans flag `-output`/`-Format` (`backend/app/tools/definitions/nikto.yaml`).
- Suite de tests isolée de la base de données de développement : `backend/tests/conftest.py` bascule automatiquement vers `<POSTGRES_DB>_test` (créée si absente) — un run pytest précédent avait pollué la base de dev avant cette correction.
- Vérifié de bout en bout : création de job via l'API, mise à jour `QUEUED → RUNNING → SUCCESS` reçue en temps réel par WebSocket, annulation propre dans les deux cas (`QUEUED` et `RUNNING`) sans écrasement ultérieur.
- `docs/api.md` ajouté.

## Unreleased — Phase 3 — Tool Registry + parsers

- Tool Registry déclaratif (`backend/app/tools/`) : définitions YAML pour `nmap`, `whatweb`, `nikto` (`definitions/*.yaml`), schéma pydantic (`schema.py`), chargement + validation d'intégrité au démarrage (`registry.py`).
- `build_command()` valide strictement les paramètres utilisateur (types `target`/`url`/`string`/`boolean`/`choice`/`integer`, anti flag-injection, anti métacaractères shell, allowlist des arguments connus) avant de générer la liste d'arguments envoyée à l'agent Kali — défense en profondeur en complément de la validation déjà faite côté agent (Phase 2).
- Parsers de sortie (`backend/app/tools/parsers/`) : nmap (XML via `defusedxml`, anti-XXE), whatweb (JSON), nikto (texte) → résultats normalisés.
- `run_registered_tool_job()` (`backend/app/jobs/tasks.py`) : relie registre → agent Kali → parser en une seule tâche RQ.
- Endpoints `GET /api/tools` et `GET /api/tools/{name}`.
- 18 tests unitaires (validation des arguments, injection, parsers, anti-XXE).
- Vérifié de bout en bout : job `nmap` enregistré via le registre, exécuté par le worker, résultat parsé et normalisé récupéré via RQ. Un test avec `-sV` a aussi validé l'application du timeout et la gestion propre d'une sortie XML tronquée (`parse_error`).
- `docs/tools.md` ajouté.

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
