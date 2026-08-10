# API

Documentation interactive générée automatiquement par FastAPI : `http://localhost:8300/docs` (Swagger UI) et `/redoc`.

## Santé

- `GET /api/health` — liveness.
- `GET /api/health/db` — vérifie la connexion PostgreSQL.

## Projects

- `GET /api/projects?search=&status=` — liste les projets avec compteurs (`target_count`/`job_count`/`finding_count`/`lab_count` — ce dernier vaut toujours `0` pour l'instant, le Lab Manager n'ayant pas encore de notion de projet, voir limitation ci-dessous).
- `POST /api/projects` — `{name, description?}` → crée un projet (`201`).
- `GET /api/projects/{id}` — détail + compteurs (`404` si inconnu).
- `PATCH /api/projects/{id}` — met à jour `name`/`description`/`status` (`ACTIVE`/`ARCHIVED`).
- `DELETE /api/projects/{id}` — `204` si vide, `409` s'il reste des targets rattachées (pas de suppression en cascade silencieuse).
- `GET /api/projects/{id}/targets` — targets du projet.
- `POST /api/projects/{id}/targets` — crée une target rattachée à ce projet.

### Limitation connue

`lab_count` est actuellement toujours `0` : le Lab Manager (`labmanager/`) n'a pas encore de notion de `project_id`/`target_id` — un lab lancé n'est pas rattaché à un projet. Documenté honnêtement plutôt que simulé ; à traiter dans une phase future.

## Targets

- `GET /api/targets?project_id=&target_type=&authorization_status=` — liste filtrable.
- `GET /api/targets/{id}` — détail (`404` si inconnu).
- `PATCH /api/targets/{id}` — met à jour n'importe quel champ, y compris `authorization_status` — **action humaine uniquement**, jamais atteignable depuis l'IA (voir [ai.md](ai.md) et [security.md](security.md)).
- `DELETE /api/targets/{id}` — `204`. Les jobs déjà exécutés contre cette target ne sont pas supprimés (`target_id` passe à `NULL`, voir modèle de données dans [architecture.md](architecture.md)).
- `GET /api/targets/{id}/jobs` — historique des jobs de cette target.

### Autorisation (`authorization_status`)

`UNKNOWN` (défaut) | `LAB` | `AUTHORIZED` | `LOCAL`. Seuls `LAB`/`AUTHORIZED`/`LOCAL` autorisent la création d'un job via `target_id` (`POST /api/jobs` renvoie `403` sinon) — logique centralisée dans `backend/app/targets/authorization.py::is_executable`. Auto-inférence à la création pour `localhost`/`127.0.0.1`/les hostnames de lab (`cyberlab-lab-*`, `cyberlab-kali`) ; toute autre cible démarre `UNKNOWN` et doit être marquée manuellement.

## Outils (Tool Registry — voir [tools.md](tools.md))

- `GET /api/tools` — liste les outils disponibles et leurs paramètres.
- `GET /api/tools/{name}` — détail d'un outil (404 si inconnu).

## Jobs (Job Engine)

- `POST /api/jobs` — crée et met en file un job. Deux façons de désigner la cible, mutuellement exclusives :
  ```json
  {"tool": "nmap", "target": "10.0.0.5", "options": {"ports": "80,443", "service_detection": true}, "timeout": 60}
  ```
  ```json
  {"tool": "nmap", "target_id": "3b1e...-uuid", "options": {"service_detection": true}}
  ```
  Avec `target_id` : la target est résolue en base, `project_id`/`target_id` sont enregistrés sur le job, et son `authorization_status` est vérifié — `403` si elle n'est pas `LAB`/`AUTHORIZED`/`LOCAL` (voir [security.md](security.md)). Avec `target` en texte libre : aucune vérification d'autorisation, comportement historique inchangé (Phases 3–9). Dans les deux cas, validation du registre (allowlist d'outils, arguments) exécutée **avant** la création en base — une requête invalide renvoie `400`/`404` sans créer de job ni le mettre en file. Réponse `201` avec le job à l'état `QUEUED`.
- `GET /api/jobs?status=&limit=&project_id=&target_id=` — liste les jobs (plus récents d'abord), filtrable par projet/target.
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

## Findings (voir [findings-reports.md](findings-reports.md))

- `GET /api/findings?severity=&job_id=&limit=` — liste les findings (plus récents d'abord).
- `GET /api/findings/{id}` — détail d'un finding (`404` si inconnu).

Les findings sont créés **automatiquement** à la fin de chaque job `SUCCESS` (`backend/app/jobs/tasks.py::execute_job`) — aucune action manuelle requise.

## Reports (voir [findings-reports.md](findings-reports.md))

- `POST /api/reports` — `{title, job_ids, format}` (`format`: `html`/`markdown`/`json`/`pdf`) → génère et persiste un rapport (`201`). `404` si aucun `job_id` valide.
- `GET /api/reports` — liste les rapports générés (métadonnées seulement).
- `GET /api/reports/{id}` — métadonnées d'un rapport.
- `GET /api/reports/{id}/download` — télécharge le contenu avec le bon `Content-Type`/`Content-Disposition`.

## IA (voir [ai.md](ai.md))

- `POST /api/ai/analyze/{job_id}` — analyse IA d'un job terminé, persistée sur `Job.ai_analysis`.
- `POST /api/ai/plan` — `{target, goal}` ou `{target_id, goal}` → plan proposé (jamais exécuté automatiquement). Avec `target_id`, le contexte réel (autorisation, jobs/findings précédents) est injecté dans le prompt et chaque étape du plan est estampillée `target_id` **côté serveur** — le modèle ne peut jamais inventer ni modifier la cible qu'il reçoit.
- `POST /api/ai/chat` — `{message, target_id?}` — question/réponse libre avec l'assistant, contexte de la target injecté si fournie. Aucune capacité d'exécution ni d'écriture — voir [security.md](security.md) pour les tests adversariaux qui vérifient ça noir sur blanc.

## Temps réel

- `WS /api/ws/jobs/{job_id}` — un message JSON par transition de statut (`{"id", "status", ...}`), diffusé via Redis pub/sub par le worker au fur et à mesure de l'exécution.
- `WS /api/ws/terminal` — relais transparent vers un shell interactif (PTY) confiné au conteneur `cyberlab-kali`. Protocole JSON dans les deux sens : `{"type": "stdin", "data": "..."}` / `{"type": "resize", "rows": N, "cols": M}` en entrée, `{"type": "stdout", "data": "..."}` en sortie. Voir [security.md](security.md) — c'est la surface la plus privilégiée de l'application (shell complet, pas d'allowlist).
