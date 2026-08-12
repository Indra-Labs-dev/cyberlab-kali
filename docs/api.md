# API

Documentation interactive générée automatiquement par FastAPI : `http://localhost:8300/docs` (Swagger UI) et `/redoc`.

Toutes les routes ci-dessous sont montées sous `/api`, protégées par le même middleware d'authentification optionnel (`AUTH_ENABLED`, voir [security.md](security.md)) sauf `/api/health`.

## Santé

- `GET /api/health` — liveness.
- `GET /api/health/db` — vérifie la connexion PostgreSQL.
- `GET /api/health/kali` — proxy vers l'agent Kali.
- `GET /api/health/ollama` — proxy vers Ollama.

## Projects

- `GET /api/projects?search=&status=` — liste les projets avec compteurs (`target_count`/`job_count`/`finding_count`/`lab_count` — ce dernier vaut toujours `0`, le Lab Manager n'ayant pas encore de notion de projet).
- `POST /api/projects` — `{name, description?}` → crée un projet (`201`).
- `GET /api/projects/{id}` — détail + compteurs (`404` si inconnu).
- `PATCH /api/projects/{id}` — met à jour `name`/`description`/`status` (`ACTIVE`/`ARCHIVED`).
- `DELETE /api/projects/{id}` — `204` si vide, `409` s'il reste des assets rattachés (pas de suppression en cascade silencieuse).
- `GET /api/projects/{id}/targets` / `POST /api/projects/{id}/targets` — voir section Targets (legacy).
- `GET /api/projects/{id}/assets` / `POST /api/projects/{id}/assets` — voir section Assets.

## Assets (Phase 13 — voir [phase-13-asset-model.md](phase-13-asset-model.md))

`Asset` généralise `Target` (Phase 11) : hôtes, domaines, sous-domaines, URLs, services, containers, ressources de lab. **`Target` est un alias Python de `Asset`, même table** — les deux API lisent/écrivent les mêmes lignes.

- `GET /api/assets?project_id=&type=&criticality=&authorization_status=&search=` — liste filtrable.
- `GET /api/assets/{id}` — détail (`404` si inconnu).
- `PATCH /api/assets/{id}` — met à jour n'importe quel champ éditable (`name`/`hostname`/`ip_address`/`url`/`type`/`criticality`/`authorization_status`/`tags`/`description`/`asset_metadata`). Un changement de `criticality` déclenche un recalcul asynchrone du Risk Score de tous les Findings de l'asset (Phase 15). `first_seen`/`last_seen`/`technologies` ne sont **pas** éditables (dérivés de l'activité réelle, voir Phase 13).
- `DELETE /api/assets/{id}` — `204`. Désactive proprement (`DISABLED`) tout `ScheduledJob` associé avant suppression (Phase 14).
- `GET /api/assets/{id}/jobs` — historique des jobs de cet asset.
- `GET /api/assets/{id}/risk-summary` — agrégats Risk Score (Phase 15) : `critical_findings`/`high_findings`/`medium_findings`/`low_findings`/`informational_findings`/`kev_findings`/`highest_risk_score`/`unscored_findings`.
- `GET /api/assets/{id}/schedules` / `POST /api/assets/{id}/schedules` — voir section Continuous Recon.
- `GET /api/assets/{id}/changes` — voir section Continuous Recon.
- `POST /api/projects/{id}/assets` — crée un asset rattaché à ce projet. `type` requis (`HOST`/`IP`/`DOMAIN`/`SUBDOMAIN`/`URL`/`SERVICE`/`CONTAINER`/`LAB`/`LAB_RESOURCE`/`OTHER`), `criticality` optionnel (défaut `MEDIUM`), `tags` optionnel.

### Targets (legacy, Phase 11 — inchangé depuis, voir Phase 13)

Conservé tel quel pour compatibilité ascendante — trois pages frontend (`ai`, `tools`, vue résumé de `projects/[id]`) l'utilisent encore en lecture seule, dette technique documentée dans [phase-13-asset-model.md](phase-13-asset-model.md).

- `GET /api/targets?project_id=&target_type=&authorization_status=` — liste filtrable.
- `GET /api/targets/{id}` — détail (`404` si inconnu).
- `PATCH /api/targets/{id}` — met à jour n'importe quel champ, y compris `authorization_status` — **action humaine uniquement**, jamais atteignable depuis l'IA (voir [ai.md](ai.md) et [security.md](security.md)).
- `DELETE /api/targets/{id}` — `204`. Même nettoyage des `ScheduledJob` que `DELETE /api/assets/{id}` (même table).
- `GET /api/targets/{id}/jobs` — historique des jobs de cette target.
- `POST /api/projects/{id}/targets` — crée une target (mêmes champs qu'un Asset `type`/`criticality` en moins, voir `TargetCreateRequest`).

### Autorisation (`authorization_status`)

`UNKNOWN` (défaut) | `LAB` | `AUTHORIZED` | `LOCAL`. Seuls `LAB`/`AUTHORIZED`/`LOCAL` autorisent la création d'un job via `target_id` (`POST /api/jobs` renvoie `403` sinon) — logique centralisée dans `backend/app/targets/authorization.py::is_executable`, **inchangée depuis la Phase 11** malgré les généralisations Asset/ScheduledJob des phases suivantes. Auto-inférence à la création pour `localhost`/`127.0.0.1`/les hostnames de lab (`cyberlab-lab-*`, `cyberlab-kali`) ; toute autre cible démarre `UNKNOWN` et doit être marquée manuellement.

## Outils (Tool Registry — voir [tools.md](tools.md))

- `GET /api/tools` — liste les 31 outils disponibles, avec leurs `arguments`, `profiles` (préréglages nommés) et `ai_allowed`.
- `GET /api/tools/{name}` — détail d'un outil (404 si inconnu).
- `GET /api/tools/health` — vérification non destructive par outil (`--version`/`--help` côté agent, jamais un scan réel) : `[{"name","status","detail"}]` avec `status` dans `ready`/`broken`/`not_installed`/`unknown` (agent injoignable).

## Jobs (Job Engine)

- `POST /api/jobs` — crée et met en file un job. Deux façons de désigner la cible, mutuellement exclusives, et deux façons de désigner les arguments (`profile` OU `options`) :
  ```json
  {"tool": "nmap", "target": "10.0.0.5", "options": {"ports": "80,443", "service_detection": true}, "timeout": 60}
  ```
  ```json
  {"tool": "nmap", "target_id": "3b1e...-uuid", "profile": "quick_scan"}
  ```
  Avec `target_id` : l'asset est résolu en base, `project_id`/`target_id` sont enregistrés sur le job, et son `authorization_status` est vérifié — `403` si elle n'est pas `LAB`/`AUTHORIZED`/`LOCAL`. Avec `target` en texte libre : aucune vérification d'autorisation, comportement historique inchangé (Phases 3–9), et hors du système Continuous Recon/Risk Score (aucun `target_id`, donc aucune activité/diff/risk associé). Validation du registre (allowlist d'outils, arguments) exécutée **avant** la création en base. Réponse `201` avec le job à l'état `QUEUED`. **Chemin d'autorisation partagé** avec `POST /api/schedules/{id}/run` et le ticker Continuous Recon (`app/jobs/service.py::prepare_job`, Phase 14) — jamais dupliqué.
- `GET /api/jobs?status=&limit=&project_id=&target_id=` — liste les jobs (plus récents d'abord), filtrable par projet/asset.
- `GET /api/jobs/{id}` — détail d'un job (`404` si inconnu).
- `POST /api/jobs/{id}/cancel` — annule un job `QUEUED` (retrait propre de la file) ou `RUNNING` (best effort). `400` si le job est déjà dans un état terminal.

### Statuts

`QUEUED → RUNNING → SUCCESS | FAILED` , ou `CANCELLED` à tout moment avant un état terminal.

### Limitation connue

Annuler un job `RUNNING` envoie une demande d'arrêt best-effort au worker ; le processus distant continue jusqu'à son propre timeout. Le job est marqué `CANCELLED` immédiatement côté API/DB dans tous les cas ; une correction tardive de résultat ne peut jamais écraser cet état.

## Continuous Recon + Diff Engine (Phase 14 — voir [phase-14-continuous-recon.md](phase-14-continuous-recon.md))

- `GET /api/assets/{id}/schedules` — schedules d'un asset.
- `POST /api/assets/{id}/schedules` — `{tool, profile?, params?, interval_seconds}` → crée un `ScheduledJob` (`201`). Valide l'autorisation de l'asset et le tool/profile **au moment de la création** (même validation qu'un job manuel), plancher `interval_seconds >= 300`. Premier run planifié immédiatement (`next_run_at = now()`).
- `GET /api/schedules/{id}` — détail (`404` si inconnu).
- `PATCH /api/schedules/{id}` — édite `profile`/`params`/`interval_seconds`/`status`. Passer `status: ACTIVE` depuis un autre état relance immédiatement et remet `consecutive_failures` à 0.
- `DELETE /api/schedules/{id}` — `204`, suppression définitive.
- `POST /api/schedules/{id}/run` — exécute immédiatement, même chemin d'autorisation que l'exécution automatique. `400` si le schedule est `DISABLED`.
- `GET /api/assets/{id}/changes?change_type=&severity=&before=&limit=` — timeline des `AssetChangeEvent` détectés par le Diff Engine (plus récents d'abord).

### Statuts ScheduledJob

`ACTIVE` (planifié normalement) | `PAUSED` (mis en pause manuellement, reprise possible) | `DISABLED` (asset supprimé, ou auto-désactivé après 5 échecs de planification consécutifs — nécessite une reprise manuelle explicite).

## Findings (Phase 9, Risk Score Phase 15, Corrélation/Déduplication Phase 16 — voir [findings-reports.md](findings-reports.md), [phase-15-risk-score.md](phase-15-risk-score.md), [phase-16-correlation-deduplication.md](phase-16-correlation-deduplication.md))

- `GET /api/findings?severity=&job_id=&project_id=&target_id=&priority=&kev=&min_risk_score=&status=&source_tool=&sort=&limit=` — liste les findings. `sort` : `created_at_desc` (défaut) | `risk_score_desc` | `risk_score_asc`. `priority` filtre sur `risk_priority` (`INFORMATIONAL`/`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`), `kev=true` sur les findings listés dans CISA KEV, `min_risk_score` (0–100). `status` filtre sur le cycle de vie Phase 16 (`NEW`/`CONFIRMED`/`IN_REVIEW`/`ACCEPTED_RISK`/`FALSE_POSITIVE`/`REMEDIATED`/`REOPENED`), `source_tool` sur l'outil ayant créé le finding en premier (voir `source_tools` ci-dessous pour la liste complète des outils l'ayant observé). `target_id` couvre déjà le filtre "par asset" demandé par la Phase 16 (Target=Asset depuis la Phase 13).
- `GET /api/findings/{id}` — détail d'un finding (`404` si inconnu). Inclut `cve_ids`/`cvss_score`/`epss_score`/`kev`/`risk_score`/`risk_priority`/`risk_calculated_at` (cache Risk Score, Phase 15) ainsi que `status`/`first_seen`/`last_seen`/`observation_count`/`source_tools` (cycle de vie et déduplication, Phase 16). `signature` (identité interne de déduplication) n'est volontairement pas exposé — non significatif pour un client.
- `GET /api/findings/{id}/risk` — décomposition complète du Risk Score, **recalculée en direct** (pur CPU, aucun appel réseau) : `score`, `priority`, `inputs` (cvss/epss/kev/asset_criticality/confidence avec leurs valeurs brutes), `components` (poids et disponibilité de chaque signal), `explanation` (liste de raisons lisibles).
- `GET /api/findings/{id}/history` — historique complet des changements de statut (`old_status`/`new_status`/`reason`/`triggered_by`: `manual`|`automatic`/`created_at`), plus récent en premier. `404` si le finding est inconnu.
- `GET /api/findings/{id}/relations` — Findings distincts liés par une des 3 règles de corrélation (Phase 16). Normalisé côté serveur : `finding_id` dans la réponse correspond toujours à l'ID demandé, `related_finding_id` à l'autre Finding — indépendamment de l'ordre canonique dans lequel la relation est stockée en base. Chaque entrée porte `rule` (ex. `RULE_NMAP_WHATWEB_PORT`) et `reason` (texte lisible généré par la règle, jamais un lien opaque).
- `PATCH /api/findings/{id}/status` — `{status, reason?}` fait avancer le cycle de vie (`NEW → CONFIRMED → IN_REVIEW → {ACCEPTED_RISK, FALSE_POSITIVE, REMEDIATED}`, avec réouverture manuelle possible vers `CONFIRMED`/`IN_REVIEW` depuis `REOPENED`). `400` si la transition demandée n'est pas valide depuis le statut courant (aucun état n'est modifié) ; `404` si le finding est inconnu. Chaque transition (y compris automatique, voir ci-dessous) est journalisée dans l'historique.

Les findings sont créés **automatiquement** à la fin de chaque job `SUCCESS` (`backend/app/jobs/tasks.py::execute_job`) — aucune action manuelle requise. Le Risk Score est calculé au même moment avec l'intelligence disponible à cet instant, puis recalculé après toute synchronisation EPSS/KEV/NVD pertinente ou changement de criticité de l'asset lié. Depuis la Phase 16, une observation correspondant à un finding déjà connu (même signature) **fusionne** dans la ligne existante plutôt que de créer un doublon — `observation_count` s'incrémente, `source_tools`/`observation_job_ids` s'enrichissent, et une ré-observation d'un finding `REMEDIATED`/`FALSE_POSITIVE` le fait automatiquement repasser à `REOPENED` (jamais depuis `ACCEPTED_RISK`, décision humaine protégée). La corrélation (3 règles fixes) s'exécute juste après, scopée à l'Asset du job.

## Risk Intelligence (Phase 15 — voir [phase-15-risk-score.md](phase-15-risk-score.md))

- `POST /api/intelligence/sync` — déclenche immédiatement un cycle de synchronisation EPSS + CISA KEV + NVD (via la queue RQ existante, `202 {"status": "queued"}`) au lieu d'attendre le cycle quotidien automatique. Utile pour un rafraîchissement à la demande ; ne bloque jamais sur un appel réseau.
- `GET /api/intelligence/status` — état de chaque source (`epss`/`cisa_kev`/`nvd`) : `last_attempt_at`/`last_success_at`/`last_error`/`details`.

## Reports (voir [findings-reports.md](findings-reports.md))

- `POST /api/reports` — `{title, job_ids, format}` (`format`: `html`/`markdown`/`json`/`pdf`) → génère et persiste un rapport (`201`). `404` si aucun `job_id` valide.
- `GET /api/reports` — liste les rapports générés (métadonnées seulement).
- `GET /api/reports/{id}` — métadonnées d'un rapport.
- `GET /api/reports/{id}/download` — télécharge le contenu avec le bon `Content-Type`/`Content-Disposition`.

## Labs (Lab Manager — voir [labs.md](labs.md))

- `GET /api/labs/definitions` — catalogue des labs disponibles.
- `GET /api/labs` — labs actifs (état lu directement depuis Docker).
- `POST /api/labs?definition=dvwa` — crée et démarre un lab (`201`).
- `GET /api/labs/{id}` — détail d'un lab (`404` si inconnu).
- `POST /api/labs/{id}/start` / `/stop` / `/reset` — cycle de vie.
- `DELETE /api/labs/{id}` — supprime le conteneur et son réseau dédié (`204`).

## IA (voir [ai.md](ai.md))

- `POST /api/ai/analyze/{job_id}` — analyse IA d'un job terminé, persistée sur `Job.ai_analysis`.
- `POST /api/ai/plan` — `{target, goal}` ou `{target_id, goal}` → plan proposé (jamais exécuté automatiquement). Chaque étape peut porter un `tool` **et** un `profile`, tous deux revalidés contre le Tool Registry réel après génération. Avec `target_id`, le contexte réel (autorisation, jobs/findings précédents) est injecté dans le prompt et chaque étape est estampillée `target_id` **côté serveur**.
- `POST /api/ai/chat` — `{message, target_id?}` — question/réponse libre, contexte de l'asset injecté si fourni. Aucune capacité d'exécution ni d'écriture.

## Temps réel

- `WS /api/ws/jobs/{job_id}` — un message JSON par transition de statut (`{"id", "status", ...}`), diffusé via Redis pub/sub par le worker au fur et à mesure de l'exécution.
- `WS /api/ws/terminal` — relais transparent vers un shell interactif (PTY) confiné au conteneur `cyberlab-kali`. Protocole JSON dans les deux sens : `{"type": "stdin", "data": "..."}` / `{"type": "resize", "rows": N, "cols": M}` en entrée, `{"type": "stdout", "data": "..."}` en sortie. Voir [security.md](security.md) — c'est la surface la plus privilégiée de l'application (shell complet, pas d'allowlist).

## Historique des dettes documentaires corrigées

Ce document n'avait pas été mis à jour lors de l'introduction d'Asset (Phase 13) ni de Continuous Recon (Phase 14) — corrigé intégralement en Phase 15 pour refléter l'état réel des 31 routeurs montés, pas seulement les ajouts de cette phase.
