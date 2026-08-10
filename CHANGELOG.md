# Changelog

## Unreleased — Phase 11 — Projects + Targets + hardening

- **`Project` and `Target` models, for real** (`backend/app/models/project.py`,
  `backend/app/models/target.py`): closes the gap Phase 5 documented honestly
  ("not yet implemented" placeholder pages) rather than faked with mock data.
  `Project`: id, name, description, status (`ACTIVE`/`ARCHIVED`), timestamps.
  `Target`: id, `project_id` (mandatory FK), name, hostname/ip_address/url,
  `target_type` (`HOST`/`IP`/`DOMAIN`/`URL`/`CONTAINER`/`LAB`/`OTHER`),
  `authorization_status` (`UNKNOWN` default, `LAB`/`AUTHORIZED`/`LOCAL`
  executable), description, metadata. Fully additive migration
  (`6495416ebbf2`): new tables, plus nullable `project_id`/`target_id` on
  `jobs` with `ondelete="SET NULL"` — deleting a Project/Target never
  destroys job history.
- **Target authorization as a real security boundary**
  (`backend/app/targets/authorization.py`): `POST /api/jobs` is the single
  enforcement point — a `target_id` resolving to an `UNKNOWN`-status target
  is rejected with `403` before a job is ever created, regardless of caller
  (frontend, AI planner, curl). Auto-inferred to `LAB`/`LOCAL` for
  localhost/127.0.0.1/Docker lab hostnames at creation time; everything else
  starts `UNKNOWN` and needs an explicit human `PATCH`.
- **Full REST APIs**: `backend/app/api/routes/projects.py` (CRUD + nested
  targets, rollup counts, `409` on delete-with-targets),
  `backend/app/api/routes/targets.py` (filtered list, CRUD, job history).
  `backend/app/api/routes/jobs.py` gained `target_id` resolution + the
  authorization check above, plus `project_id`/`target_id` filters on
  `GET /api/jobs`. See [api.md](docs/api.md).
- **Frontend**: `/projects`, `/projects/[id]` (tabs: Overview/Targets/Scans/
  Findings/Labs/AI/Reports), `/targets`, `/targets/[id]` (authorization
  controls, scan-target form using the real `target_id`) — replacing the
  Phase 5 "not yet implemented" placeholders with real, API-backed pages.
  `/ai` reworked with an active-target-context selector so AI actions are
  always grounded in a real, resolved target.
- **AI made context-aware without gaining any new power**
  (`backend/app/ai/planner.py`, `backend/app/api/routes/ai.py`): `/api/ai/plan`
  and `/api/ai/chat` accept an optional `target_id`; when given, the real
  target (authorization status, prior jobs/findings) is injected into the
  prompt, and the planner stamps `target_id` onto every proposed step
  **server-side, never from model output** — the AI can never invent or
  swap a target. Adversarial black-box tests
  (`backend/tests/ai/test_ai_security_boundary.py`) prove this holds even
  against a fake provider that actively lies about having executed shell
  commands or changed authorization: the database stays untouched in every
  case, and two static tests assert `app/ai/` has zero `subprocess`/`docker`
  imports and zero write access to the `Target` model.
- **Tool Registry gained risk levels** (`SAFE`/`CAUTION`/`RESTRICTED` on
  every YAML definition — `whatweb: SAFE`, `nmap: CAUTION`, `nikto:
  RESTRICTED`), surfaced as a badge on the `/tools` page.
- **Docker Socket Proxy replaces direct `docker.sock` access for the Lab
  Manager**: new `cyberlab-docker-proxy` service
  (`tecnativa/docker-socket-proxy`) holds the only mount of the real socket
  (read-only), exposing just `CONTAINERS`/`NETWORKS`/`IMAGES`/`POST` over
  HTTP on the internal network — `EXEC`/`VOLUMES`/`SYSTEM`/`SECRETS`/`SWARM`
  all explicitly denied. `cyberlab-labmanager` now connects via
  `DOCKER_HOST=tcp://cyberlab-docker-proxy:2375` (the Docker SDK's
  `docker.from_env()` already honors `DOCKER_HOST`, so `docker_manager.py`
  needed zero code changes) and, no longer needing raw socket-file
  permissions, now runs as a **non-root user** with `cap_drop: ALL` — the
  last non-root exception in the stack is gone. Verified live: full lab
  lifecycle (create → running with a real published port → actual DVWA
  HTTP response → stop → delete, container and dedicated network both
  cleaned up) replayed end-to-end through the proxy.
- **RBAC (ADMIN/ANALYST/USER) evaluated and deliberately deferred**: the API
  has no user identity today (a single shared bearer token), so attaching a
  role to a request has nothing to attach it to without introducing a `User`
  model and login — exactly the "major rework" the spec said to avoid if
  RBAC wasn't feasible without one. Documented in
  [security.md](docs/security.md) along with what already exists that
  covers part of the same need (the Policy Engine at job creation, and
  `authorization_status` as a resource-level rather than user-level
  boundary).
- **`AUTH_ENABLED` coverage extended**: new parametrized regression test
  (`test_every_api_route_is_guarded_when_auth_enabled`) walks every router
  mounted under `/api` — including easy-to-forget ones like
  `/api/reports/{id}/download`, `/api/labs/definitions`, `/api/ai/plan` —
  plus a dedicated `/api/ws/terminal` WebSocket-auth test that had no
  coverage before.
- **Final structured security audit** (18 categories, PASS/DEFERRED per
  category with justification) appended to
  [security.md](docs/security.md#phase-11--audit-de-sécurité-final). One
  honest non-PASS worth calling out here: `POST /api/jobs` still accepts a
  free-text `target` with no `target_id`, inherited unchanged from Phases
  3–9 (the classic Tools page) — that path has no `Target` row to check, so
  `authorization_status` doesn't apply to it. This is a documented, scoped
  gap (the legacy manual-tool-run flow), not a regression: every path that
  matters for this phase's stated goal — the AI, and the new Targets UI —
  always goes through `target_id` and is fully enforced.
- New backend tests: `backend/tests/projects/` (11), `backend/tests/targets/`
  (16, split across CRUD and authorization), `backend/tests/ai/
  test_ai_security_boundary.py` (6 adversarial AI security tests), plus
  additions to `backend/tests/api/test_jobs.py`, `backend/tests/ai/
  test_planner.py`, `backend/tests/tools/test_registry.py`, and
  `backend/tests/test_auth_middleware.py` — full suite (113 tests) green.

## Unreleased — Phase 10 — Security hardening pass

- **Optional bearer-token authentication** for the API (`AUTH_ENABLED`, disabled
  by default — CyberLab binds to `127.0.0.1` only out of the box). Pure ASGI
  middleware (`backend/app/core/auth_middleware.py`, not `BaseHTTPMiddleware`)
  so it can also guard WebSocket upgrades, not just HTTP. `/api/health` stays
  reachable unauthenticated (container healthchecks). WebSocket auth via
  `?token=` query param (browsers can't set custom headers on a WS handshake);
  spec-compliant rejection (receives `websocket.connect` before sending
  `websocket.close(code=4401)`). Closes a real gap: `API_SECRET_KEY` had
  existed unused in config since Phase 1. Frontend (`useApi.ts`) auto-attaches
  the token via `apiFetch`/`wsUrl`/`downloadUrl` when
  `NUXT_PUBLIC_API_TOKEN` is set; `docker-compose.yml` wires it from
  `API_SECRET_KEY` only when `AUTH_ENABLED` is set. 8 new tests
  (`backend/tests/test_auth_middleware.py`). Verified live: full stack
  restarted with `AUTH_ENABLED=true`, confirmed 401 without a token / 200
  with the right one via curl, and the Nuxt UI kept working transparently
  (dashboard, running a scan, live WebSocket status) with zero visible
  change for the user; then reverted to the disabled default.
- **Real XSS found and fixed** in HTML reports: `html_renderer.py` used
  `jinja2.Template(...)` without `autoescape=True`. Finding titles/
  descriptions can reflect content from the scanned target (tool output,
  e.g. nikto echoing a raw `<script>` tag found on a page) — without
  escaping, that content was injected verbatim into the report HTML.
  Fixed with `autoescape=True`; regression test added.
- **Real markup-injection issue found and fixed** in PDF reports:
  `pdf_renderer.py` interpolated the same kind of scan-derived content
  directly into reportlab's XML-like Paragraph markup unescaped — could
  break PDF generation on malformed input, or let crafted content spoof
  report formatting (e.g. `<font color="white">` to hide text). Fixed with
  `xml.sax.saxutils.escape` on every data-derived value; regression test
  added.
- Dependency audit: `npm audit` clean (0 vulnerabilities). `pip-audit`
  found 11 CVEs across 3 packages; bumped `python-dotenv` (1.0.1->1.2.2)
  and `jinja2` (3.1.5->3.1.6), both safe patch versions. `starlette`
  (0.41.3, 6 CVEs) needs a FastAPI major-version bump incompatible with
  the current pin (`fastapi==0.115.6` requires `starlette<0.42`) --
  deferred rather than rushed this late without a full regression pass;
  tracked in docs/security.md.
- Code review swept for `shell=True`, `os.system`/`os.popen`, `eval`/
  `exec`, `pickle`, f-string SQL across backend/kali-agent/labmanager --
  no occurrences found.
- Reviewed CORS (never wildcard, scoped to the frontend origin) and
  container users (non-root everywhere except `cyberlab-labmanager`,
  which needs `docker.sock` -- documented, accepted trade-off).
- Documented remaining known gaps rather than silently leaving them
  unstated: starlette CVEs, no API rate limiting, best-effort RUNNING-job
  cancellation, Markdown reports not HTML-escaping embedded content.

## Unreleased — Phase 9 — Findings + Reports

- Finding model (`backend/app/models/finding.py`): job_id, target, source_tool,
  title, description, severity (INFO..CRITICAL), confidence, evidence (raw
  tool data), recommendation. Extracted **automatically** on job SUCCESS
  (`backend/app/findings/extractor.py`, wired into `execute_job()`) — one
  extractor per tool (nmap: open ports only; whatweb: detected tech;
  nikto: per finding line, MEDIUM only on vuln keywords), deliberately
  conservative on severity (never HIGH/CRITICAL from a heuristic alone).
  `GET /api/findings`, `GET /api/findings/{id}`.
- Report model (`backend/app/models/report.py`): persisted, regenerable
  without recomputation. `backend/app/reports/builder.py` aggregates
  jobs + findings + AI analysis; renderers for json/markdown/html (Jinja2)/
  pdf (reportlab, pure Python — no Cairo/Pango system deps). `POST /api/reports`,
  `GET /api/reports`, `GET /api/reports/{id}/download`.
- Frontend: `/findings` page (severity filter, links back to the source
  scan), `/reports` page (select completed scans, pick a format, generate,
  download past reports).
- Real bug found via end-to-end testing against the DVWA lab (not just the
  Kali container scanning itself): nmap's default host-discovery ping
  (ICMP/ARP) needs `CAP_NET_RAW` independently of `-sT`, so any scan of a
  real external target failed with "Couldn't open a raw socket or eth
  handle". Fixed by adding `-Pn` to nmap's fixed_args (skip host discovery,
  treat target as up) — documented in `docs/security.md`.
- Real, more significant bug found and fixed: `server_default="now()"` (a
  bare Python string) on Job/Finding/Report was compiled by SQLAlchemy as
  the literal SQL string `'now()'`; Postgres evaluates that cast once, at
  table-creation time, then reuses the same frozen timestamp as the default
  for every row — so every row in a table shared the same `created_at`
  until the table was recreated. Fixed with `sa.text("now()")` (an unquoted
  function call, re-evaluated per row) plus a migration
  (`6ad0daaf9daa`) correcting the already-live columns. Documented in
  `docs/findings-reports.md`.
- Verified end-to-end: ran nmap + whatweb against the running DVWA lab,
  confirmed findings were extracted automatically (1 + 14), generated
  reports in all four formats through the actual browser UI, downloaded
  and inspected each (PDF confirmed as a real 2-page PDF via `file`,
  Markdown/JSON/HTML content spot-checked).

## Unreleased — Phase 8 — AI integration (Ollama)

- `backend/app/ai/`: provider abstraction (`provider.py` interface, `ollama.py`
  implementation) so the model/backend can be swapped later without touching
  `analyst.py`/`planner.py`. Structured-output prompts (`prompts.py`) using
  Ollama's `format: "json"` constraint, with tolerant JSON extraction
  (`parsing.py`) for when a small local model wraps its answer in prose or
  markdown fences anyway.
- **AI Analyst** (`POST /api/ai/analyze/{job_id}`): analyzes a completed
  job's tool/target/parsed result/stdout, returns/persists a structured
  `{risk, summary, findings, recommendations, next_steps}` on `Job.ai_analysis`
  (new column, migration `566dc8667e8a`). Falls back to `risk: INFO` with the
  raw response preserved if the model's output isn't parseable, rather than
  erroring.
- **AI Mission Planner** (`POST /api/ai/plan`): given `{target, goal}`,
  grounds the model in the real Tool Registry (only tools that actually
  exist are ever proposed; a hallucinated tool name is stripped rather than
  trusted) and returns a proposed step-by-step plan. It never executes
  anything itself — the frontend only runs a step when the user explicitly
  clicks "Run" on it, through the same `POST /api/jobs` path (and therefore
  the same strict registry validation) as the Tools page.
- **AI Assistant chat** (`POST /api/ai/chat`): free-form Q&A, no execution
  capability.
- Frontend: `/ai` page (chat + Mission Planner with per-step "Run"), and an
  "Analyze with AI" panel on the scan detail page.
- 11 new tests (`backend/tests/ai/`): JSON extraction edge cases, analyst
  fallback behavior, planner tool-hallucination stripping.
- Real-world finding from end-to-end testing with the local model
  (`qwen2.5-coder:3b`): it frequently proposes slightly malformed tool
  options (e.g. a full nmap flag string instead of a port list, an
  aggression level outside the allowed choices) — in every case the Tool
  Registry's validation rejected the request with a clear error before any
  call reached the Kali agent, confirmed live via the actual browser UI.
  Documented in `docs/ai.md` and `docs/security.md` as the intended
  defense-in-depth behavior, not a bug.

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
