# Changelog

## Unreleased — Phase 7 — Lab Manager

- New `cyberlab-labmanager` service (`labmanager/`): the only service in the
  stack with `docker.sock` mounted, isolated from `cyberlab-api`/`cyberlab-worker`.
  Resolves the tension between "never give the backend docker.sock" and
  needing to actually control Docker to run vulnerable-by-design labs — by
  containing that access to one narrow, single-purpose service instead.
- Declarative lab catalog (`labmanager/definitions/*.yaml`), same pattern as
  the Tool Registry. One lab to start: DVWA (`vulnerables/web-dvwa`).
- Lifecycle via Docker labels as the single source of truth (no duplicated
  state in Postgres): create/start/stop/reset/delete/list, each lab on its
  own Docker network plus a connection to `cyberlab-kali-net` so the Kali
  container can scan it by name, host port published on 127.0.0.1 only.
- `cyberlab-api` proxies `GET/POST /api/labs...` to the lab manager over an
  internal authenticated HTTP call (`backend/app/api/routes/labs.py`), same
  shared-token pattern as the Kali agent.
- Real bug found and fixed via end-to-end testing: the Docker SDK is
  synchronous; calling it directly inside an `async def` FastAPI route
  blocked the entire event loop for the duration of an image pull —
  including `/health`, making the service fully unresponsive meanwhile.
  Fixed by offloading every Docker SDK call to a thread
  (`loop.run_in_executor`).
- Frontend `/labs` page: running labs with live status/URL and
  start/stop/reset/delete actions, plus a launchable catalog.
- `docs/security.md` documents the `docker.sock` trade-off honestly: it's
  still host-root-equivalent access, container-level hardening (cap_drop,
  no-new-privileges) would be security theater given the socket mount — the
  real mitigation is functional isolation to one narrow service.
- Verified end-to-end in the actual browser: launched DVWA from the UI,
  confirmed it's reachable both from the host and from the Kali container
  (by container name), tested stop/start/reset, deleted it and confirmed
  both the container and its dedicated network were fully removed.
- 8 new tests (`labmanager/tests/`): lab catalog validation, and auth
  rejection (missing/wrong/unset token) for the lab manager's endpoints.

## Unreleased — Phase 6 — Integrated terminal

- Kali agent (`kali/agent/main.py`) gains a `WS /terminal` endpoint: opens a real PTY (`pty.openpty()` + `bash` via `subprocess.Popen(preexec_fn=os.setsid)`), relays stdin/stdout/resize as JSON frames, authenticated with the same shared `KALI_AGENT_TOKEN` as tool execution.
- `cyberlab-api` gains `WS /api/ws/terminal` (`backend/app/api/routes/terminal.py`): a transparent byte-relay between the browser and the Kali agent's terminal socket — the API never opens a shell itself, keeping the PTY confined to the isolated Kali container with no `docker.sock` involved.
- Frontend `/terminal` page: xterm.js + `@xterm/addon-fit`, SSR disabled for this route (xterm references browser globals), dynamic import to keep it fully client-side.
- Bugs found and fixed during end-to-end testing:
  - `onUnmounted` was being registered after an `await` inside `onMounted`, which breaks Vue's lifecycle-hook tracking — cleanup (closing the socket/PTY) silently never ran. Fixed by declaring cleanup state at top-level scope and registering `onUnmounted` synchronously.
  - The Kali agent called `proc.terminate()` on disconnect but never `proc.wait()`, leaving `bash <defunct>` zombie processes in the container after every terminal session. Fixed with `await loop.run_in_executor(None, proc.wait)`.
- New tests (`kali/agent/tests/test_terminal_auth.py`): missing token, wrong token, and agent started without `AGENT_TOKEN` configured all reject the WebSocket with `close(code=4401)` — no silent fallback to "auth disabled" for the app's most privileged endpoint.
- Verified end-to-end: connected from the actual browser UI, ran real commands (`echo`, `nmap --version`) inside the Kali container's shell and saw live output; confirmed no zombie processes remain after disconnecting.
- `docs/security.md` updated with a dedicated section flagging the terminal as the highest-privilege surface in the app (full shell, no allowlist) and the hard requirement for user auth before any exposure beyond `localhost`.

## Unreleased — Phase 5 — Dashboard UI (Nuxt)

- Sidebar layout (`frontend/app/layouts/default.vue`) with the full navigation from the spec (Dashboard, Projects, Targets, Tools, Scans, Labs, Terminal, AI Assistant, Findings, Reports, Settings).
- Dashboard (`/`): real system status tiles (API, DB, Kali, Ollama — no fake data), active jobs, recent scans. Backed by two new endpoints, `GET /api/health/kali` and `GET /api/health/ollama` (both proxy through the backend; the frontend never talks to the Kali agent or Ollama directly).
- Tools (`/tools`): lists the Tool Registry and renders a form per tool generated from its argument definitions (target/url/string/boolean/choice), submits to `POST /api/jobs`, redirects to the scan detail page.
- Scans (`/scans`, `/scans/[id]`): job list and a live detail view subscribed to `WS /api/ws/jobs/{id}` (`useJobSocket` composable) showing status, timestamps, parsed result, stdout/stderr, and a cancel button.
- Targets, Projects, Labs, Terminal, AI Assistant, Findings, Reports pages exist and are navigable but show an explicit "not yet implemented" state (`ComingSoon` component) rather than fake/mock data, since their backend models don't exist yet.
- Settings (`/settings`): shows the actual configured API/WS base URLs.
- Verified in-browser end to end: ran an nmap job from the Tools form, watched it resolve to `SUCCESS` with a real parsed result on the scan detail page, and confirmed it appears in the Scans list. No console errors.

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
