# Phase 14 — Continuous Recon + Diff Engine

## Objectif

Transformer un scan ponctuel en surveillance périodique : planifier des scans récurrents sur un Asset (Phase 13), et comparer automatiquement chaque nouveau résultat au précédent pour détecter des changements réels (port ouvert/fermé, technologie ajoutée/retirée, certificat modifié, statut HTTP changé).

## Audit initial — écarts avec la roadmap

Avant implémentation, vérification du commit `1e1ce0c` (Phase 13) et de l'état réel du repo :

- `Target` **est** `Asset` (alias Python vers la même table `assets`, confirmé — pas de divergence de données possible).
- Trois pages frontend (`ai/index.vue`, `tools/index.vue`, `projects/[id].vue`) utilisent encore `/api/targets` en lecture seule (sélecteurs de cible, résumé de projet) — elles ne manipulent rien qui diffère de `/api/assets` puisque ce sont les mêmes lignes. **Décision** : dette technique documentée, laissée intacte (ces pages ne font rien de faux, juste incomplet côté champs Phase 13 affichés) ; tout le code Phase 14 (nouveau) utilise exclusivement `Asset`/`/api/assets`, jamais `/api/targets`.
- Aucune divergence trouvée entre la roadmap fournie et le code réel pour les Phases 1–13.

## Architecture retenue

```
Asset
 ↓
ScheduledJob (Postgres, pas de nouveau moteur)
 ↓
Ticker (thread en arrière-plan dans cyberlab-worker, pas de nouveau service)
 ↓
app.jobs.service.prepare_job() + app.targets.authorization.is_executable()
 (exactement le même chemin que POST /api/jobs)
 ↓
Job Engine existant (RQ, cyberlab-kali)
 ↓
Normalized Result (parsers existants, Phase 3/12)
 ↓
Diff Engine (app/diff/) — comparaison avec le dernier Job compatible
 ↓
AssetChangeEvent (Postgres)
 ↓
Timeline (page Asset)
```

**Aucun nouveau service Docker, aucune nouvelle dépendance externe** (pas de RQ Scheduler, pas d'APScheduler, pas de Kafka/RabbitMQ, pas de Redis Lock). Le ticker est un `threading.Thread` démarré dans le process `cyberlab-worker` existant (`app/jobs/worker.py`), qui a déjà l'accès DB synchrone et Redis/RQ nécessaires.

### Pourquoi un thread dans le worker plutôt qu'un service séparé

Options évaluées :
- **RQ Scheduler** : processus dédié supplémentaire (`rqscheduler`), donc soit un nouveau service Docker, soit un second process dans un conteneur existant (contraire aux conventions Docker "un process par conteneur" sans bénéfice réel ici).
- **APScheduler dans `cyberlab-api`** : aurait fonctionné, mais mélange requêtes HTTP et boucle de fond dans le même process ASGI, et le test de restart demandé par le spec ("redémarrer le worker") aurait été moins pertinent.
- **Thread dans `cyberlab-worker` (retenu)** : le worker a déjà tout ce qu'il faut (session sync Postgres via `app/db/sync_session.py`, connexion Redis/RQ via `app/jobs/queue.py`, et surtout `execute_job()` lui-même). Un thread démon (`daemon=True`) ne bloque jamais l'arrêt du conteneur ; s'il redémarre, le thread repart avec lui et relit `next_run_at` depuis Postgres — rien n'est perdu puisque l'état vit en base, pas en mémoire.

## Modèle : ScheduledJob

`backend/app/models/scheduled_job.py`, table `scheduled_jobs` :

| Champ | Rôle |
|---|---|
| `asset_id` | FK `assets.id`, `ON DELETE SET NULL` — voir section suppression ci-dessous |
| `project_id` | dénormalisé depuis `asset.project_id` à la création (même pattern que `Job.project_id`) |
| `tool` / `profile` / `params` | mêmes types que `Job` — validés à la création ET à chaque exécution via `app.jobs.service.prepare_job()` |
| `interval_seconds` | intervalle fixe (pas de cron) — **choix délibéré de simplicité** : couvre l'exemple de la spec ("toutes les 6 heures") sans dépendance à un parseur cron. `MIN_INTERVAL_SECONDS = 300` (5 min) empêché en dessous (anti-abus) |
| `status` | `ACTIVE` / `PAUSED` / `DISABLED` |
| `next_run_at` | calculé côté serveur uniquement — jamais un champ éditable par l'API (voir schémas) |
| `last_run_at`, `last_job_id` | dernière exécution réussie (au sens "un Job a été créé", pas au sens "le scan a réussi") |
| `consecutive_failures`, `last_error` | échecs de *planification* (pas d'exécution) — voir Retry/Failure |

Le premier run est planifié immédiatement (`next_run_at = now()` à la création) plutôt qu'après un intervalle complet, pour établir la baseline rapidement — même choix que `Asset.first_seen` en Phase 13.

### Suppression d'Asset

`DELETE /api/assets/{id}` et `DELETE /api/targets/{id}` (même table) appellent désormais `app.scheduling.service.disable_schedules_for_asset()` **dans la même transaction** que la suppression : tout `ScheduledJob` pointant sur l'asset passe à `DISABLED` avec `last_error = "asset deleted"` avant que la ligne `Asset` ne disparaisse. Le FK `ON DELETE SET NULL` est un filet de sécurité (au cas où l'asset serait supprimé par un autre chemin), pas le mécanisme principal — vérifié par test que les deux routes de suppression déclenchent bien la désactivation.

## Scheduler / Ticker (`app/scheduling/ticker.py`)

### Réservation (idempotence, pas de doublon)

```python
SELECT * FROM scheduled_jobs
WHERE status = 'ACTIVE' AND next_run_at <= now()
ORDER BY next_run_at
LIMIT 50
FOR UPDATE SKIP LOCKED
```

`next_run_at` est avancé et **committé immédiatement**, avant toute autre opération (création du Job, appel à `queue.enqueue`). C'est la réservation Postgres native demandée par le spec plutôt qu'un verrou Redis :

- Un crash entre la réservation et le traitement coûte au pire une exécution manquée (la ligne n'est jamais bloquée indéfiniment) — testé (`test_claiming_twice_immediately_does_not_double_claim`).
- Deux connexions concurrentes ne peuvent jamais réserver la même ligne due (`FOR UPDATE SKIP LOCKED`) — testé avec deux vraies sessions Postgres séparées (`test_concurrent_claim_skip_locked_prevents_double_claim`), pas seulement simulé.

### Même chemin que l'exécution manuelle

`app/jobs/service.py::prepare_job()` a été extrait de `POST /api/jobs` (Phase 11-13) et est appelé identiquement par :
- `POST /api/jobs` (manuel, via API async)
- `POST /api/assets/{id}/schedules` (validation à la création)
- `POST /api/schedules/{id}/run` (exécution manuelle immédiate)
- `app/scheduling/ticker.py::process_schedule()` (exécution automatique)

Et `app.targets.authorization.is_executable()` (inchangé depuis la Phase 11) est appelé par les quatre mêmes chemins avant toute création de Job. Aucun de ces quatre chemins n'a de logique d'autorisation dupliquée ou différente.

### Retry / Failure

Un `ScheduledJob` ne peut pas créer une boucle infinie :
- Un échec de *planification* (asset non autorisé, tool/profile invalide) incrémente `consecutive_failures` et enregistre `last_error`, mais laisse le statut `ACTIVE` — l'échec peut être transitoire (l'autorisation peut être restaurée).
- Après `MAX_CONSECUTIVE_FAILURES = 5` échecs consécutifs, le schedule passe automatiquement à `PAUSED` — un humain doit intervenir (`PATCH .../schedules/{id}` avec `status: ACTIVE`, qui remet `consecutive_failures` à 0 et relance immédiatement).
- Un Job créé avec succès mais qui échoue *à l'exécution* (le scan lui-même rate) ne compte **pas** comme un échec de planification — le schedule a fait son travail (déclencher un Job réel) ; `consecutive_failures` est remis à 0 dès qu'un Job est créé avec succès, indépendamment du résultat final de ce Job.
- Un schedule dont le traitement lève une exception inattendue est capturé (`except Exception` dans `process_schedule`) et journalisé, **sans jamais interrompre le tick des autres schedules** — testé (`test_bad_schedule_does_not_block_others_in_the_same_tick`).

## Diff Engine (`app/diff/`)

### Comparabilité

Deux Jobs sont comparables si : même `target_id` (Asset), même `tool`, même `profile`, même `params` (égalité stricte du dict). `app/diff/service.py::find_previous_comparable_job()` cherche uniquement parmi les 20 Jobs `SUCCESS` les plus récents pour le même Asset+tool (limite volontaire — pas de scan de tout l'historique, cf. exigence de performance), puis filtre en Python sur `profile`/`params`. Aucun Job précédent compatible → aucun changement généré, ce Job devient simplement la nouvelle baseline.

### Détections implémentées (et limites documentées honnêtement)

| Catégorie | Outil | Détecté | Non détecté (parser actuel ne le fournit pas) |
|---|---|---|---|
| Réseau | nmap | port ouvert/fermé, service/produit/version changé | — |
| Technologies | whatweb | technologie ajoutée/retirée/changée (résumé version/string) | — |
| Web | whatweb | statut HTTP changé | changement de titre de page comme catégorie séparée (whatweb l'expose comme un plugin `Title` parmi d'autres — traité comme `TECHNOLOGY_CHANGED`, pas une catégorie HTTP dédiée) |
| TLS | sslscan | certificat : `subject` et `not_valid_after` changés | **issuer et fingerprint — non détectés**, `app/tools/parsers/sslscan.py` ne les extrait pas actuellement. Pas simulé, documenté honnêtement plutôt que de prétendre les couvrir. |
| Endpoints | gobuster | nouvel endpoint découvert / disparu (`change_type: OTHER`, aucun nouveau type inventé pour ça) | — |

`nikto`, `nuclei`, `masscan`, `searchsploit` et les 22 outils à `parser: none` (sortie brute, voir `docs/tools.md`) ne sont **pas** diffés — `app/diff/engine.py::SUPPORTED_TOOLS` liste explicitement les 4 outils couverts ; tout autre outil produit une liste de changements vide plutôt qu'une fausse détection.

### AssetChangeEvent

9 types (`PORT_OPENED`, `PORT_CLOSED`, `SERVICE_CHANGED`, `TECHNOLOGY_ADDED`, `TECHNOLOGY_REMOVED`, `TECHNOLOGY_CHANGED`, `CERTIFICATE_CHANGED`, `HTTP_CHANGED`, `OTHER`) — exactement ceux listés dans la spec, aucun ajouté. Sévérité réutilise l'enum `Finding.Severity` existant (pas de nouvelle échelle) : `PORT_OPENED`/`SERVICE_CHANGED`/`CERTIFICATE_CHANGED` = `MEDIUM` (mérite l'attention), `PORT_CLOSED` = `LOW`, le reste = `INFO` — jugement conservateur cohérent avec `app/findings/extractor.py` (Phase 9).

`ON DELETE CASCADE` sur `asset_id` : l'historique de changements d'un Asset n'a pas de sens sans l'Asset (contrairement à `Job`, conservé pour audit même après suppression du Project/Target en Phase 11/13) — décision documentée, pas un oubli.

## API

```
GET    /api/assets/{id}/schedules
POST   /api/assets/{id}/schedules      (validation complète : autorisation + tool/profile/params)
GET    /api/schedules/{id}
PATCH  /api/schedules/{id}             (pause/reprise, édition profile/params/interval)
DELETE /api/schedules/{id}
POST   /api/schedules/{id}/run         (exécution immédiate, même chemin d'autorisation)
GET    /api/assets/{id}/changes        (filtres change_type/severity, pagination limit/before)
```

Toutes protégées par le même middleware d'authentification que le reste de `/api/*` (vérifié explicitement dans `test_every_api_route_is_guarded_when_auth_enabled`). `next_run_at`/`last_run_at`/`last_job_id`/`consecutive_failures` sont absents de `ScheduledJobUpdateRequest` — jamais assignables directement par l'API, seulement dérivés par le ticker/les routes d'exécution.

## Frontend

Page Asset (`frontend/app/pages/targets/[id].vue`) enrichie de deux sections, branchées exclusivement sur `/api/assets/{id}/schedules` et `/api/assets/{id}/changes` (jamais `/api/targets`) :

- **Continuous Recon** : tableau des schedules (tool/profile, fréquence, statut, prochain run relatif, dernier run avec lien vers le scan), formulaire de création (tool → profils dynamiques → fréquence par préréglages), actions Pause/Reprendre/Exécuter maintenant/Supprimer par ligne. États loading/error/empty.
- **Change Timeline** : liste triée par date décroissante, icône par sévérité (🟢/🟡/🔴), résumé lisible généré côté frontend à partir de `change_type`/`field` (jamais du HTML injecté depuis `old_value`/`new_value` — interpolation Vue échappée), filtres change_type/severity, lien vers le Job source. États loading/error/empty.

## Vérification end-to-end réelle

Contre le stack Docker complet, pas seulement des tests unitaires :

1. **Diff réel avec changement d'environnement contrôlé** : asset `cyberlab-kali`, scan baseline (port 8888 fermé), ouverture réelle d'un listener (`nc -l -p 8888` via `docker exec`), second scan → `PORT_OPENED` détecté et persisté. Fermeture du listener, troisième scan → `PORT_CLOSED` détecté. Vérifié via l'API et le navigateur.
2. **Scheduler réel** : `ScheduledJob` créé (intervalle 5 min), premier run automatique observé dans les logs `cyberlab-worker` moins de 15s après création (poll interval), `last_job_id`/`last_run_at`/`next_run_at` mis à jour correctement.
3. **Redémarrage du worker pendant un schedule actif** : `docker compose restart cyberlab-worker`, log `scheduler ticker started` réapparaît, le schedule forcé à échéance après le restart se déclenche normalement (nouveau `last_job_id`, `consecutive_failures` à 0) — aucune perte, aucun doublon.
4. **UI réelle** : création d'un schedule via le formulaire du navigateur, "Run now" sur un schedule en pause (fonctionne, comportement voulu), suppression, timeline affichant les deux changements réels avec horodatage relatif et lien vers le scan.
5. Nettoyage complet (schedules, asset, projet de test supprimés), logs `cyberlab-api`/`cyberlab-worker` vérifiés sans erreur.
6. Suite de tests complète (207 tests, dont 52 nouveaux) rejouée contre une base `_test` fraîchement recréée : verte.

## Sécurité

Voir la section dédiée dans [security.md](security.md#phase-14--continuous-recon--diff-engine--audit-de-sécurité).

## Limites connues / hors scope de cette phase

- Pas de cron expressions — intervalle fixe uniquement (`interval_seconds`). Documenté comme choix de simplicité, pas une contrainte technique difficile à lever plus tard si le besoin apparaît.
- Certificat TLS : issuer et fingerprint non comparés (parser sslscan actuel ne les extrait pas).
- Le Diff Engine ne couvre que 4 outils (nmap, whatweb, sslscan, gobuster) sur les 31 du Tool Registry — les autres n'ont pas de sortie structurée exploitable pour un diff honnête.
- Pas de notification (email/webhook) sur un changement détecté — la Timeline est consultée activement, pas poussée. Hors scope Phase 14, pourrait être une extension future si un vrai besoin apparaît.
- Le chemin `POST /api/jobs` avec `target` en texte libre (sans `target_id`, hérité des Phases 3–9) reste hors du système Asset/Schedule/Diff, comme il est déjà hors du système d'autorisation — comportement inchangé, pas une régression de cette phase.
