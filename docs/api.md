# API

Documentation interactive générée automatiquement par FastAPI : `http://localhost:8300/docs` (Swagger UI) et `/redoc`.

## Santé

- `GET /api/health` — liveness.
- `GET /api/health/db` — vérifie la connexion PostgreSQL.

## Outils (Tool Registry — voir [tools.md](tools.md))

- `GET /api/tools` — liste les outils disponibles et leurs paramètres.
- `GET /api/tools/{name}` — détail d'un outil (404 si inconnu).

## Jobs (Job Engine)

- `POST /api/jobs` — crée et met en file un job.
  ```json
  {
    "tool": "nmap",
    "target": "10.0.0.5",
    "options": {"ports": "80,443", "service_detection": true},
    "timeout": 60
  }
  ```
  Validation du registre (allowlist d'outils, arguments) exécutée **avant** la création en base — une requête invalide renvoie `400`/`404` sans créer de job ni le mettre en file. Réponse `201` avec le job à l'état `QUEUED`.
- `GET /api/jobs?status=&limit=` — liste les jobs (plus récents d'abord).
- `GET /api/jobs/{id}` — détail d'un job (`404` si inconnu).
- `POST /api/jobs/{id}/cancel` — annule un job `QUEUED` (retrait propre de la file) ou `RUNNING` (best effort, voir limitation ci-dessous). `400` si le job est déjà dans un état terminal.

### Statuts

`QUEUED → RUNNING → SUCCESS | FAILED` , ou `CANCELLED` à tout moment avant un état terminal.

### Limitation connue

Annuler un job `RUNNING` envoie une demande d'arrêt best-effort au worker (`rq.command.send_stop_job_command`), mais le processus distant (nmap/whatweb/nikto) tournant dans le conteneur Kali continue jusqu'à son propre timeout — l'agent Kali n'expose pas encore de mécanisme pour tuer un scan en cours par identifiant. Le job est marqué `CANCELLED` immédiatement côté API/DB dans tous les cas ; une correction tardive de résultat ne peut jamais écraser cet état (voir `backend/app/jobs/tasks.py::execute_job`).

## Labs (Lab Manager — voir [labs.md](labs.md))

- `GET /api/labs/definitions` — catalogue des labs disponibles.
- `GET /api/labs` — labs actifs (état lu directement depuis Docker).
- `POST /api/labs?definition=dvwa` — crée et démarre un lab (`201`).
- `GET /api/labs/{id}` — détail d'un lab (`404` si inconnu).
- `POST /api/labs/{id}/start` / `/stop` / `/reset` — cycle de vie.
- `DELETE /api/labs/{id}` — supprime le conteneur et son réseau dédié (`204`).

## Temps réel

- `WS /api/ws/jobs/{job_id}` — un message JSON par transition de statut (`{"id", "status", ...}`), diffusé via Redis pub/sub par le worker au fur et à mesure de l'exécution.
- `WS /api/ws/terminal` — relais transparent vers un shell interactif (PTY) confiné au conteneur `cyberlab-kali`. Protocole JSON dans les deux sens : `{"type": "stdin", "data": "..."}` / `{"type": "resize", "rows": N, "cols": M}` en entrée, `{"type": "stdout", "data": "..."}` en sortie. Voir [security.md](security.md) — c'est la surface la plus privilégiée de l'application (shell complet, pas d'allowlist).
