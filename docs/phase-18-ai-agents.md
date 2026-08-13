# Phase 18 — Agents spécialisés (IA)

Livraison réelle de la Phase 18 planifiée dans [roadmap.md](roadmap.md#phase-18--agents-spécialisés-dans-le-policy-engine-existant). Autonomie **Niveau 2 — Execute Approved Tasks** : un humain approuve un plan entier en une fois, puis chaque étape s'exécute automatiquement, mais re-validée individuellement par le Policy Engine avant de partir — jamais un chemin d'exécution parallèle à `POST /api/jobs`.

## Ce qui est livré, et ce qui ne l'est pas

| Niveau | Statut réel après Phase 18 |
|---|---|
| 0 — Advisor | Déjà là (chat, Phase 11). |
| 1 — Suggest | Déjà là (Mission Planner / `POST /api/ai/plan`, Phase 11). |
| **2 — Execute Approved Tasks** | **Livré.** `Mission`/`MissionStep` + `MissionOrchestrator` : un plan approuvé une fois exécute ses étapes l'une après l'autre, sans reconfirmation humaine par étape. |
| 3 — Execute Mission Workflow | **Non livré comme autonomie complète.** Les fondations nécessaires le sont : kill switch (`cancel_mission`), `max_steps`, re-vérification `is_executable()` à chaque étape, verrouillage anti-concurrence — mais aucun enchaînement conditionnel ("si l'étape N trouve X, lancer Y") n'existe. Une Mission suit une liste fixe, décidée une fois par `AIMissionPlanner` à la création, jamais modifiée en cours de route par le modèle. |
| 4 — Autonomous Lab Operations | **Non livré, hors scope de cette phase.** |

## Architecture

```text
app/ai/
  orchestrator.py   — MissionOrchestrator.create_mission() (async) +
                       approve_mission()/advance_mission()/cancel_mission()
                       (sync, module-level)
  agents/
    correlation.py  — CorrelationAgent (lecture seule)
    report.py       — ReportAgent (lecture seule)
  planner.py         — AIMissionPlanner (Phase 11, réutilisé sans modification)
  analyst.py          — AIAnalyst (Phase 11, réutilisé sans modification)

app/models/
  mission.py                    — Mission, MissionStep (nouveau)
  ai_correlation_suggestion.py  — AICorrelationSuggestion (nouveau)

app/api/routes/ai.py — routes Mission/Correlation/Report ajoutées au
                        routeur existant, /plan, /analyze, /chat inchangés
```

Pas de nouveau microservice : `MissionOrchestrator` est un module Python de plus dans `app/ai/`, appelé depuis les routes FastAPI existantes (`app/api/routes/ai.py`, déjà monté) et depuis `app/jobs/tasks.py::execute_job` (déjà le point d'entrée RQ). À ne pas confondre avec le **Tool Orchestrator** prévu pour la Phase 21 — celui-ci enchaînera conditionnellement plusieurs outils *au sein d'un seul Job*, un problème différent de la progression d'une Mission d'un `Job` au suivant.

### La divergence de conception la plus importante : pas de `create_job()` unifié

Le design initial supposait une fonction `create_job()` unique, appelable aussi bien depuis une route async que depuis un contexte sync. L'inspection du code réel (`app/jobs/service.py`, `app/scheduling/ticker.py`, `app/jobs/tasks.py`) a montré que ce clivage async/sync est **déjà** une décision architecturale assumée du projet, documentée dans le docstring de `app/jobs/service.py` : les routes FastAPI utilisent `AsyncSession`, le worker RQ et le ticker Phase 14 utilisent `Session` (sync) via `get_sync_session()`.

`app/scheduling/ticker.py::process_schedule` est déjà un second appelant indépendant de `is_executable()` + `prepare_job()`, sans jamais passer par `POST /api/jobs`. `MissionOrchestrator` en devient un **troisième**, en suivant exactement le même patron (verrouillage, relecture, `is_executable()`, `prepare_job()`, construction manuelle du `Job`, `queue.enqueue()`) — pas une quatrième mécanique de création de Job. Conséquence directe : **`app/jobs/service.py` et `app/api/routes/jobs.py` ne sont pas modifiés par cette phase.**

### `create_mission()` (async) vs `approve_mission()`/`advance_mission()`/`cancel_mission()` (sync, module-level)

- `MissionOrchestrator.create_mission()` est la seule méthode async, et la seule à avoir besoin du provider IA (`AIMissionPlanner.plan()`, appel réseau à Ollama). Elle s'exécute directement sur l'`AsyncSession` de la route, exactement comme `POST /api/ai/plan` aujourd'hui.
- `approve_mission()`/`advance_mission()`/`cancel_mission()` ne touchent jamais le provider IA — ce sont des fonctions **module-level**, pas des méthodes de `MissionOrchestrator`, pour ne pas forcer un faux provider à leurs appelants (notamment `execute_job()`, qui n'a et ne doit avoir aucune notion d'IA). Elles ouvrent leur propre session sync (`get_sync_session()`), verrouillent la ligne `Mission`, agissent, commitent, ferment. Appelées à la fois depuis la route async (via `asyncio.to_thread`, le même idiome que `app/api/routes/assets.py::recalculate_findings_for_asset_sync`) et directement depuis `execute_job()` (déjà sync).

### `advance_mission()` — la séquence de sécurité complète

1. `SELECT ... FOR UPDATE` **bloquant** (pas `SKIP LOCKED`) sur la `Mission` — un second appel concurrent doit attendre, puis relire l'état déjà à jour et devenir un no-op, jamais sauter la ligne ou dupliquer un `Job`. Contraste volontaire avec `ticker.py::claim_due_schedules`, qui verrouille un lot de lignes indépendantes et *skippables* (`SKIP LOCKED`) — une seule `Mission` n'est jamais "skippable", elle doit être traitée par exactement un appelant à la fois.
2. Un statut `Mission` terminal (`COMPLETED`/`FAILED`/`CANCELLED`) est un no-op immédiat — idempotence.
3. **Réconciliation** : si l'étape courante est `QUEUED`, son `Job` est relu ; tant qu'il n'a pas atteint un statut terminal (`SUCCESS`/`FAILED`/`CANCELLED`), rien ne se passe. C'est cette étape qui transforme "le Job a fini" en "la MissionStep a fini" — `execute_job()` n'écrit jamais directement dans `MissionStep`.
4. Stop-on-failure, sans retry dans cette phase : un `FAILED`/`SKIPPED` sur une étape termine la Mission en `FAILED` ; un `CANCELLED` (Job annulé directement, hors `cancel_mission()`) termine la Mission en `CANCELLED`.
5. `max_steps` est un plafond dur, revérifié ici indépendamment de la troncature déjà faite à la création — défense en profondeur.
6. Avant chaque nouvelle étape : rechargement serveur de l'`Asset` cible et **nouvel appel à `is_executable()`** — jamais de confiance dans l'état d'autorisation qu'avait la cible à l'approbation. Une autorisation révoquée entre deux étapes fait passer l'étape courante à `SKIPPED` (jamais de `Job` créé) et arrête la Mission.
7. `prepare_job()` (identique à celui utilisé par `ticker.py`/`POST /api/jobs`) construit et valide les arguments ; un échec de validation (outil halluciné jamais nettoyé par le planner, tool inconnu) passe l'étape en `SKIPPED` plutôt que `FAILED` — `FAILED` est réservé au cas où un vrai `Job` a réellement échoué (voir la contrainte `ck_mission_step_job_id_required_when_executed`, qui interdit `FAILED`/`SUCCESS`/`QUEUED` sans `job_id`).
8. Sinon : `Job` créé, `queue.enqueue()`, `MissionStep.job_id`/`status = QUEUED`, `Mission.status = RUNNING`, commit unique.

### Isolation Job ↔ Mission dans `execute_job()`

`app/jobs/tasks.py::execute_job()` est désormais un mince wrapper : `_execute_job()` (le corps historique, inchangé) tourne dans un `try`, et le hook `advance_mission_for_job(job_id)` s'exécute dans le `finally` **le plus externe** — donc après que la session du Job se soit refermée et que son statut terminal soit déjà committé, y compris sur le chemin `except Exception: ... raise`. Le hook ouvre sa **propre** session, entièrement isolée, dans un `try`/`except` qui journalise et avale toute erreur sans jamais pouvoir réécrire `job.status`. Un bug dans `advance_mission_for_job()` ne peut donc jamais transformer un `Job` `SUCCESS` en `FAILED` a posteriori — vérifié explicitement par `tests/jobs/test_mission_integration.py::test_job_stays_success_even_if_mission_advancement_fails`.

## Correlation Agent — jamais un raccourci vers `FindingRelation`

`FindingRelation` (Phase 16) reste réservée aux 3 règles déterministes de `app/findings/correlation.py`. Le Correlation Agent (`app/ai/agents/correlation.py`) est **entièrement en lecture seule** — pas d'accès `Session`, aucune capacité d'écriture, il reçoit des `Finding` déjà chargés et renvoie des `CorrelationSuggestion` pydantic (jamais un objet ORM). Ses suggestions sont persistées par la route (`app/api/routes/ai.py`) dans la table dédiée `ai_correlation_suggestions` (`status: PENDING`), **jamais** en écrivant un `source="ai_suggested"` sur `FindingRelation`.

Une suggestion ne devient une vraie `FindingRelation` que via `POST /api/ai/correlation-suggestions/{id}/accept` — un clic humain explicite. Cette route duplique volontairement le tri canonique par UUID (`sorted((a, b), key=str)`) déjà utilisé par `_create_relation_if_new` plutôt que d'importer cette fonction privée d'un autre module, et écrit la relation avec un `rule` distinct (`RULE_AI_ACCEPTED`), toujours traçable comme d'origine IA. Idempotent : accepter deux fois la même suggestion ne crée jamais une deuxième `FindingRelation`.

## Report Agent — jamais un raccourci vers un vrai rapport

`app/ai/agents/report.py::ReportAgent`, également en lecture seule, ne connaît ni `build_report_data()`, ni `render()`, ni le modèle `Report`. `propose()` renvoie une `ReportProposal` (titre + `job_ids` + justification), jamais générée ni persistée elle-même. Le flux imposé reste : Report Agent → `ReportProposal` → édition humaine (titre/liste de scans modifiable dans l'UI) → `POST /api/reports`, **le même endpoint inchangé** que la génération manuelle depuis `/reports`. Vérifié en conditions réelles (voir plus bas) : le rapport généré depuis une proposition apparaît dans "Past reports" au même titre qu'un rapport créé manuellement.

## API ajoutée (`app/api/routes/ai.py`)

`/plan`, `/analyze/{job_id}`, `/chat` restent inchangées. Nouveau :

| Route | Description |
|---|---|
| `POST /api/ai/missions` | Crée une Mission `DRAFT` (target_id obligatoire, jamais choisi par le modèle). |
| `GET /api/ai/missions` | Liste, filtrable par `target_id`. |
| `GET /api/ai/missions/{id}` | Détail avec ses `MissionStep`. |
| `POST /api/ai/missions/{id}/approve` | `DRAFT → APPROVED`, déclenche `advance_mission()`. |
| `POST /api/ai/missions/{id}/cancel` | Kill switch — jamais un `Job` en cours. |
| `POST /api/ai/correlation-suggestions` | Génère (et persiste, idempotent) des suggestions pour un `target_id`. |
| `GET /api/ai/correlation-suggestions` | Liste par `target_id`. |
| `POST /api/ai/correlation-suggestions/{id}/accept` | Crée la `FindingRelation` réelle. |
| `POST /api/ai/correlation-suggestions/{id}/dismiss` | Rejette, idempotent. |
| `POST /api/ai/reports/propose` | `ReportProposal` pour un `project_id`. |

## Frontend (`/ai/missions`)

Nouvelle page distincte du Mission Planner existant sur `/ai` (qui reste inchangé : plan + `Run` étape par étape via `POST /api/jobs`). Trois sections : Missions (création, statuts DRAFT/APPROVED/RUNNING/COMPLETED/FAILED/CANCELLED via `MissionStatusBadge`, étapes via `MissionStepStatusBadge`, Approve/Cancel, polling borné pendant `RUNNING`), Correlation Suggestions (étiquette **"Suggestion IA"** visuellement distincte des relations déterministes, Accept/Reject), Report Proposal (titre et liste de scans éditables avant `Generate`, qui appelle `POST /api/reports` sans toucher au flux `/reports` existant).

## Vérification réelle (Docker + navigateur)

Migration `f8721b028a2d` appliquée sur la vraie base de dev (backup pris avant, cycle upgrade → downgrade → upgrade vérifié). Conteneurs `cyberlab-api`/`cyberlab-worker`/`cyberlab-frontend` reconstruits et redémarrés avec le code réel de cette phase.

Test de bout en bout contre l'Asset DVWA réel et Ollama réel (`qwen2.5-coder:3b`) :
1. Mission créée avec un objectif en langage naturel → 6 étapes réelles proposées par le modèle (`amass`, `arp-scan`, `nmap`, `nikto`, ... — pas seulement `nmap`/`whatweb`/`nikto`, la liste `ai_allowed` réelle est plus large).
2. Approve → premier `Job` (`amass`) créé et enfilé → repris par le vrai worker RQ → appel réel à l'agent Kali (`POST http://cyberlab-kali:9000/exec`, `200 OK`) → le `Job` termine `FAILED` (`amass` échoue avec une erreur `sudo`/conteneur non liée à cette phase — un vrai résultat d'outil, pas une simulation).
3. Le hook post-completion d'`execute_job()` a correctement réconcilié l'étape en `FAILED`, arrêté la Mission (`FAILED`), et laissé les 5 étapes suivantes `PENDING` sans y toucher — la politique "stop-on-failure, jamais de retry" fonctionne de bout en bout, sans intervention manuelle.
4. Report Proposal : proposition réelle générée par le modèle pour un projet existant, titre édité, `Generate` → rapport réellement créé via `POST /api/reports` et visible dans "Past reports" (`/reports`) au même titre qu'un rapport manuel.

## Tests

58 nouveaux tests backend (456 au total) : cycle de vie de Mission (DRAFT/approbation/progression/COMPLETED/FAILED/CANCELLED), sécurité (autorisation révoquée en cours de mission, `target_id` jamais choisi par le modèle, `max_steps` appliqué même avec des lignes en trop, outil halluciné), **concurrence réelle à deux threads/deux sessions** prouvant qu'un seul `Job` est jamais créé pour une même étape, isolation Job/Mission (`Job` reste `SUCCESS` même si l'avancement de la Mission échoue), Correlation Agent (lecture seule, aucune `FindingRelation` créée à la génération, accept/dismiss idempotents), Report Agent (jamais de `Report` créé), routes API, et garde-fous statiques étendus à `app/ai/agents/`/`orchestrator.py` (pas de `subprocess`/`docker`, pas d'import de `Target`, pas d'accès `Session` dans les agents). 25 nouveaux tests frontend (93 au total).

## Ce qui n'est délibérément pas fait

- Pas de retry automatique sur un `Job`/une étape échoué·e.
- Pas d'enchaînement conditionnel entre étapes (Niveau 3 réel).
- Pas de nouveau chemin d'exécution : chaque `Job` créé par une Mission passe par `is_executable()` + `prepare_job()`, identique à tout autre `Job`.
- Aucune modification de `app/jobs/service.py`, `app/api/routes/jobs.py`, `app/reports/*`, ou du flux `/reports` existant.
