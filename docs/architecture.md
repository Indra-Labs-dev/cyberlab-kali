# Architecture

## Vue d'ensemble

```
Nuxt (frontend, :3300) --REST/WS--> FastAPI (api, :8300) --+--> PostgreSQL (:55432)
                                                            +--> Redis (:63790) <--> Worker RQ
                                                            +--> Kali container (réseau isolé cyberlab-kali-net)
                                                            +--> Ollama (hôte, :11434)
```

## Services Docker Compose

| Service | Rôle | Réseau(x) | Port hôte |
|---|---|---|---|
| `cyberlab-frontend` | Nuxt 4 UI | cyberlab-backend | 3300 |
| `cyberlab-api` | FastAPI (REST + WebSocket) | cyberlab-backend, cyberlab-kali-net | 8300 |
| `cyberlab-worker` | Worker RQ (exécution des jobs d'outils) + ticker Continuous Recon (Phase 14) + thread de sync Risk Intelligence (Phase 15) | cyberlab-backend, cyberlab-kali-net | — |
| `cyberlab-postgres` | Persistance | cyberlab-backend | 55432 |
| `cyberlab-redis` | File de jobs / pub-sub | cyberlab-backend | 63790 |
| `cyberlab-kali` | Outils de sécurité (31, voir [tools.md](tools.md)), isolé, `cap_add: [NET_RAW]` narrow depuis la Phase 12 | cyberlab-kali-net | — |
| `cyberlab-labmanager` | Cycle de vie des labs Docker (non-root) | cyberlab-backend | — |
| `cyberlab-docker-proxy` | Docker Socket Proxy — seul point de contact avec `docker.sock` | cyberlab-backend | — |

Ollama n'est **pas** conteneurisé : le backend réutilise l'instance Ollama déjà active sur l'hôte Kali (`host.docker.internal:11434`), pour ne pas dupliquer la VRAM/RAM (contrainte mémoire de la machine de développement).

## Modèle de données — Projects / Assets / Jobs (Phase 11, généralisé Phase 13)

```
Project (1) ──< Asset (N) ──< Job (N, via target_id)
   │                             │
   └──────────< Job (N, via project_id, dénormalisé pour filtrer sans jointure)
```

- **`Project`** : conteneur logique (id, name, description, status `ACTIVE`/`ARCHIVED`). Regroupe assets, jobs, findings, labs, conversations IA, reports.
- **`Asset`** (`backend/app/models/asset.py`, table `assets`) : généralisation Phase 13 du `Target` de la Phase 11 — même table (renommée), mêmes lignes, même clé primaire. Champs : id, `project_id` obligatoire, name, hostname/ip_address/url, `type` (`HOST`/`IP`/`DOMAIN`/`SUBDOMAIN`/`URL`/`SERVICE`/`CONTAINER`/`LAB`/`LAB_RESOURCE`/`OTHER`), `criticality` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`, saisie manuelle), `authorization_status`, `tags`, `technologies` (alimenté automatiquement par les résultats whatweb), `first_seen`/`last_seen` (dérivés des jobs réellement exécutés, jamais éditables), description, metadata. `authorization_status` (`UNKNOWN` par défaut, sinon `LAB`/`AUTHORIZED`/`LOCAL`) reste la **frontière de sécurité réelle** qui détermine si des jobs peuvent être lancés dessus — voir [security.md](security.md).
- **`Target`/`TargetType`** (`backend/app/models/target.py`) : alias Python purs vers `Asset`/`AssetType` (`Target = Asset`), conservés pour que tout le code et toutes les APIs de la Phase 11 (`/api/targets`, `TargetResponse`) continuent de fonctionner sans modification. Voir [phase-13-asset-model.md](phase-13-asset-model.md) pour le détail de la migration.
- **`Job.project_id` / `Job.target_id`** : optionnels, `ForeignKey(..., ondelete="SET NULL")` — supprimer un Project ou un Asset ne détruit jamais l'historique des jobs déjà exécutés, il perd juste son rattachement. Un job peut toujours être créé avec une cible en texte libre (`target`) sans passer par le modèle Asset, pour compatibilité avec le flux historique (Phases 3–9) — voir la nuance documentée dans l'audit d'autorisation de [security.md](security.md).
- **Application de l'autorisation : un seul point d'entrée, inchangé depuis la Phase 11.** `POST /api/jobs` est l'unique endroit qui vérifie `is_executable(asset)` avant de créer un job lié à un `target_id` (`backend/app/targets/authorization.py`) — ni le Mission Planner IA, ni le frontend, ni aucun autre appelant n'a de chemin de contournement. La Phase 13 n'a touché ni cette fonction ni son point d'application.
- Migration Phase 13 (`backend/alembic/versions/392e4638a4d8_...py`) : renomme `targets` → `assets` et `target_type` → `type` (Postgres met à jour la FK `jobs.target_id` automatiquement), ajoute `criticality`/`tags`/`technologies`/`first_seen`/`last_seen`, backfill `first_seen`/`last_seen` depuis l'historique des jobs existants. Aucune ligne supprimée, aucune donnée existante perdue.

## Continuous Recon + Diff Engine (Phase 14)

```
Asset ──< ScheduledJob (Postgres, réutilise le Job Engine — pas de nouveau moteur)
              │
     ticker (thread dans cyberlab-worker, pas de nouveau service)
              │
     app.jobs.service.prepare_job() + is_executable()  (même chemin que POST /api/jobs)
              │
     Job Engine existant → Normalized Result (parsers Phase 3/12)
              │
     Diff Engine (app/diff/) — comparaison avec le dernier Job compatible (même asset+tool+profile+params)
              │
     AssetChangeEvent (Postgres) → Timeline sur la page Asset
```

- **`ScheduledJob`** (`backend/app/models/scheduled_job.py`) : planifie la ré-exécution périodique d'un tool+profile+params sur un Asset. Intervalle fixe (`interval_seconds`, plancher `MIN_INTERVAL_SECONDS = 300`) plutôt qu'une expression cron — simplicité délibérée. `status` `ACTIVE`/`PAUSED`/`DISABLED`. Réservation des échéances via `SELECT ... FOR UPDATE SKIP LOCKED` + avancement immédiat de `next_run_at` (verrouillage Postgres natif, pas de verrou Redis) — voir [phase-14-continuous-recon.md](phase-14-continuous-recon.md).
- **Ticker** (`app/scheduling/ticker.py`) : thread démon dans le process `cyberlab-worker` existant (pas un service Docker séparé), poll toutes les `scheduler_poll_interval_seconds` (15s par défaut). Réutilise `app/jobs/service.py::prepare_job()` (extrait de `POST /api/jobs`) et `is_executable()` — un `ScheduledJob` ne peut jamais créer de Job en dehors du Policy Engine existant.
- **`AssetChangeEvent`** (`backend/app/models/asset_change_event.py`) : sortie du Diff Engine (`app/diff/`), qui compare les résultats normalisés de deux Jobs successifs compatibles (même Asset/tool/profile/params) pour nmap/whatweb/sslscan/gobuster. 9 types de changement, sévérité réutilisant l'enum `Finding.Severity` existant. `ON DELETE CASCADE` avec `Asset` (l'historique de changements n'a pas de sens sans l'asset).
- **Suppression d'Asset/Target** : `disable_schedules_for_asset()` (`app/scheduling/service.py`) désactive proprement (`DISABLED`) tout `ScheduledJob` associé, dans la même transaction que la suppression — jamais un schedule orphelin pointant sur un asset disparu.

## Risk Intelligence & Risk Score (Phase 15)

```
Finding (cve_ids extraits par app/tools/parsers/nuclei.py)
   │
   ├── vulnerability_intel (CVSS + EPSS, uniquement les CVE rencontrés)
   ├── cisa_kev_entries (catalogue CISA KEV complet, ~1 700 entrées, refresh quotidien)
   └── Asset.criticality + Finding.confidence (déjà en base)
              │
    app/risk/calculator.py (pur, déterministe, sans I/O)
              │
    Finding.risk_score / risk_priority (cache matérialisé, recalculé sur déclencheur)
```

- **`app/intel/`** (`epss.py`/`cisa_kev.py`/`nvd.py`/`sync.py`) : clients HTTP vers FIRST.org EPSS, CISA KEV, NVD CVE API 2.0 — schémas vérifiés en conditions réelles (voir [phase-15-risk-score.md](phase-15-risk-score.md)). Ingestion scopée aux CVE réellement rencontrés (EPSS/NVD) ou à un catalogue borné et justifié (CISA KEV, ~1,5 Mo, pas d'API de requête par CVE). Thread de fond dans `cyberlab-worker` (`start_intel_sync_thread`), **distinct** du ticker Continuous Recon — pattern réutilisé (thread + état Postgres), pas le modèle `ScheduledJob` (spécifique à l'exécution d'outils Kali).
- **`app/risk/calculator.py`** : moyenne pondérée normalisée de 3 signaux disponibles (CVSS-ou-repli-sévérité 0.40, EPSS 0.35, KEV 0.25 — un signal manquant est exclu, jamais remplacé par une valeur inventée), puis multiplicateurs contextuels (criticité Asset ×0.85–1.30, confidence Finding ×0.60–1.00). Formule complète et justification mathématique dans [phase-15-risk-score.md](phase-15-risk-score.md).
- **`Finding`** gagne `cve_ids`/`cvss_score`/`epss_score`/`kev`/`risk_score`/`risk_priority`/`risk_calculated_at` — cache matérialisé (jamais la source de vérité), recalculé à l'extraction, après sync d'intelligence, et après changement de `Asset.criticality`.
- Aucun appel réseau externe synchrone dans un chemin de lecture — `GET /api/findings/{id}/risk` recalcule en direct mais uniquement à partir de données déjà locales (pur CPU).

## Décisions architecturales

- **File de jobs : RQ plutôt que Celery.** Plus léger (pas de broker AMQP séparé), suffisant pour des jobs d'outils CLI séquentiels/parallèles, cohérent avec Redis déjà présent dans la stack.
- **Aucun accès direct à `docker.sock` depuis l'API/worker, ni même depuis le Lab Manager.** Depuis la Phase 11, seul `cyberlab-docker-proxy` (Docker Socket Proxy) touche le socket réel ; `cyberlab-labmanager` s'y connecte en HTTP (`DOCKER_HOST=tcp://...`) avec une surface d'API Docker restreinte (pas d'`EXEC`/`VOLUMES`/`SYSTEM`). Voir [security.md](security.md).
- **Ports hôte remappés** (3300/8300/55432/63790) pour cohabiter avec d'autres stacks Docker locales utilisant les ports par défaut.
- **Tool Registry déclaratif (YAML)** : chaque outil Kali est décrit par un fichier de définition (exécutable, arguments typés/validés, parser de sortie, niveau de risque `SAFE`/`CAUTION`/`RESTRICTED`/`MANUAL_ONLY`), jamais codé en dur côté frontend. Depuis la Phase 12, 31 outils curés (pas un dump de la distribution Kali — voir [tools.md](tools.md) pour le détail des inclusions/exclusions), chacun avec des **profils** (préréglages nommés d'arguments, validés par la même couche que le mode manuel) et un champ `ai_allowed` réellement appliqué : un outil `ai_allowed: false` n'est jamais inclus dans le prompt envoyé au modèle, pas seulement filtré après coup.
- **IA sans accès direct à l'exécution.** Flux imposé : `Utilisateur → IA → Intention structurée (JSON) → Job Engine (POST /api/jobs, Policy Engine + Tool Registry) → Agent Kali → Résultat → IA (analyse)`. L'IA ne détient ni `subprocess`, ni `docker.sock`, ni accès en écriture au modèle `Target` — vérifié par des tests statiques en plus des tests fonctionnels (`backend/tests/ai/test_ai_security_boundary.py`). Voir [ai.md](ai.md) et [security.md](security.md).
