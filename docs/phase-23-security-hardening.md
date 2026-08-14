# Phase 23 — Security & Execution Hardening

Phase de consolidation, pas fonctionnelle : aucun nouveau système métier, aucune nouvelle capacité IA, aucun nouveau tool, aucun changement de niveau d'autonomie IA, aucune fusion Mission/Chain. Déclenchée par un audit global post-roadmap (Phases 1-22, 6 agents indépendants) et exécutée en respectant une règle stricte : **chaque finding a été re-vérifié directement dans le code/la DB réels avant toute correction**, jamais accepté depuis la documentation seule.

## P0 — bypass réels fermés

### `/docs`/`/redoc`/`/openapi.json` non protégés

`app/core/auth_middleware.py` ne gardait que les chemins sous `/api` (`path.startswith("/api")`) — les endpoints d'introspection FastAPI par défaut n'y sont jamais passés. Confirmé en direct (`curl` sur l'instance réellement lancée, `AUTH_ENABLED=true` + `BIND_ADDRESS=0.0.0.0`) : `/openapi.json` retournait 200 sans token pendant que `/api/jobs` retournait correctement 401. Une fuite de reconnaissance complète (tout le schéma API) sur un hôte exposé au réseau.

Corrigé en étendant l'ensemble des chemins gardés (`_DOCS_PATHS`), réutilisant exactement le même mécanisme d'authentification (`_extract_token()`/`_reject()`) — pas de bypass parallèle. Un développeur peut toujours ouvrir Swagger UI via `?token=<secret>` dans l'URL, exactement comme un client WebSocket le fait déjà (un navigateur ne peut pas attacher un header `Authorization` custom à une simple navigation de page).

### Bypass d'autorisation via target texte libre sur `POST /api/jobs`

`request.target_id is not None` gate le seul appel à `is_executable()` dans `create_job()` — la branche `else` (target texte libre, documentée comme "ad-hoc quick scans" et réellement utilisée par un toggle UI sur `/tools`) ne passait jamais par la Policy Engine. N'importe qui avec le token pouvait pointer n'importe lequel des 31 outils contre n'importe quel hôte Internet.

La fonctionnalité n'a pas été supprimée (elle est réellement utilisée) : elle est désormais classifiée via `infer_default_authorization()` — la même fonction déjà utilisée à la création d'un Asset — et refusée si le résultat n'est pas LAB/LOCAL/AUTHORIZED. `app/targets/authorization.py::is_status_executable()` a été extrait pour partager exactement le même prédicat de policy entre le chemin `target_id` (un `Target`/`Asset` réel) et le chemin texte libre (un statut inféré, sans ligne DB).

Une seconde fenêtre a été fermée dans la même passe : la fenêtre TOCTOU entre la création d'un Job (autorisation vérifiée une fois) et son exécution réelle par le worker (jamais re-vérifiée). `_execute_job()` re-vérifie désormais `is_executable()` juste avant `run_tool()` pour tout Job avec un `target_id` — fermant cette fenêtre pour les **4 créateurs de Job simultanément** (une seule correction, pas 4), puisqu'ils convergent tous vers `execute_job()`.

## P1 — robustesse opérationnelle

### Rate limiting (`app/core/rate_limit.py`)

Compteurs Redis à fenêtre fixe (`INCR`/`EXPIRE`), réutilisant l'instance Redis déjà requise pour RQ — pas de nouveau système distribué. Appliqué comme dépendance FastAPI sur les endpoints qui créent un vrai travail (création de Job/ChainRun/Report, appels IA), jamais un middleware global sur les GET. Désactivé par défaut (`RATE_LIMIT_ENABLED=false`), même convention que `AUTH_ENABLED` — à activer ensemble en exposant une instance au-delà de localhost.

### AI Memory TOCTOU (`app/ai/memory.py`)

`regenerate_project_summary()` faisait une lecture puis écriture sans verrou — deux Jobs d'un même projet finissant à quelques secondes d'intervalle pouvaient tous deux voir `existing is None` et tenter un `INSERT`, le second levant une `IntegrityError` non gérée sur `uq_project_ai_summary_project`. Corrigé par un `INSERT ... ON CONFLICT (project_id) DO UPDATE` atomique — la lecture du cooldown reste simple/non verrouillée (elle ne décide que d'appeler ou non le LLM, sans incidence sur la correction de l'écriture finale). Un bug réel a été trouvé et corrigé pendant l'implémentation : `session.execute(select(...))` après le `INSERT ... ON CONFLICT` retournait l'objet déjà en cache dans l'identity map de la session (chargé par la lecture du cooldown plus haut dans la même fonction), pas la ligne fraîchement écrite — corrigé avec `execution_options(populate_existing=True)`.

### Stratégie commit/enqueue unifiée

`routes/jobs.py`/`ticker.py` faisaient `commit()` puis `enqueue()` ; `orchestrator.py`/`chains/service.py` faisaient `flush()` puis `enqueue()` puis `commit()`. Les deux ordres ont des modes d'échec différents en cas de crash entre les deux opérations. Standardisé sur **`flush → enqueue → commit`** partout — pas l'inverse, car c'est le seul ordre compatible avec le verrou `SELECT ... FOR UPDATE` que Mission/Chain tiennent jusqu'à la toute fin de leur transaction (inverser aurait relâché le verrou avant l'écriture finale et cassé leur garantie de concurrence déjà testée). Mode d'échec résiduel documenté : un crash entre `enqueue()` et `commit()` laisse un job RQ orphelin référençant un `Job` jamais committé — `execute_job()` gère déjà ce cas silencieusement (`if job is None: return`).

### Réconciliation (`app/jobs/reconciliation.py`)

Ni PostgreSQL ni Redis/RQ ne peuvent être une seule transaction — aucun ordre commit/enqueue ne peut fermer la fenêtre où Redis perd un job qu'il avait déjà accepté (redémarrage sans persistance, éviction TTL, crash du worker en cours d'exécution). Sweep minimal, thread de fond dans le worker existant (même patron que le ticker Phase 14/le sync Phase 15, pas un nouveau service) : Jobs `QUEUED`/`RUNNING` depuis plus de 30 minutes (largement au-delà du `max_timeout` du plus long outil du Tool Registry) sans entrée RQ correspondante → `FAILED` avec un message explicite. Jamais de ré-enfilement automatique silencieux — un Job qui a peut-être réellement tourné contre une vraie cible ne doit jamais être rejoué sans un humain qui le décide explicitement.

### Indexes (migration `e5f1a9c7d3b2`)

`jobs` (7 autres tables y ont une FK) n'avait aucun index secondaire malgré des filtres constants sur `project_id`/`target_id`/`status`/`created_at`. `findings.job_id` et `assets.project_id` de même. Ajoutés : `ix_jobs_project_id`, `ix_jobs_target_id`, `ix_jobs_status`, `ix_jobs_created_at`, `ix_findings_job_id`, `ix_assets_project_id`.

### Bug de downgrade Alembic (`6495416ebbf2`)

`op.drop_constraint(None, 'jobs', type_='foreignkey')` (×2) — reliquat d'autogénération jamais finalisé (`# please adjust!` toujours présent), noms de contraintes jamais résolus. Corrigé avec les noms réels confirmés en base (`jobs_project_id_fkey`, `jobs_target_id_fkey`). **Seul `downgrade()` a changé** — `upgrade()` et tout état déjà appliqué sur une base réelle restent intacts, conformément à la règle "ne jamais modifier le comportement forward d'une migration historique".

Un second bug du même downgrade a été trouvé uniquement en testant réellement le round-trip complet (pas en le lisant) : les 3 types ENUM Postgres créés par cette migration (`project_status`, `target_type`, `target_authorization_status`) n'étaient jamais droppés par `op.drop_table()`, faisant échouer tout ré-upgrade avec `type "project_status" already exists`. Corrigé dans la même passe.

## P2 — dette de test

- **Fixtures `VulnerabilityIntel.cve` codées en dur** (`VulnerabilityIntel.cve` est une clé primaire) : 11 sites dans `tests/risk/test_service.py`, `tests/risk/test_risk_api.py`, `tests/intel/test_sync.py` rendus idempotents (get-or-create, même pattern déjà utilisé pour `IntelSyncState`/`CisaKevEntry` dans ces mêmes fichiers). En prouvant réellement la correction (3 exécutions consécutives sans recréer la base de test), 3 fragilités supplémentaires du même type ont été trouvées : deux tests dont la prémisse ("cette valeur est nouvelle/inconnue") était cassée par une ligne laissée par une exécution précédente, et un cas plus profond où `sync_nvd_cvss()` (fonction de production, appelée sans mock sur la base entière) traite tout CVE non scoré de la base de test partagée — pas seulement ceux de son propre fixture. Les trois corrigés avec le même principe (nettoyer explicitement sa propre précondition plutôt que supposer une base fraîche).
- **Test SKIP LOCKED du ticker** : réécrit pour appeler la vraie fonction de production (`claim_due_schedules()`) depuis un vrai thread concurrent, au lieu de réimplémenter sa requête dans le test. Découverte en cours de route : SKIP LOCKED est non-bloquant par conception (contrairement au `FOR UPDATE` bloquant de Mission/Chain) — la première version de la réécriture testait la mauvaise chose (attendait un blocage) ; corrigée pour affirmer ce qui est réellement garanti : le second appelant revient immédiatement les mains vides plutôt que de bloquer ou de double-réclamer la ligne.

## Report scoping — analysé, non implémenté

`GET /api/reports` reste sans filtrage serveur par projet. Analysé avant de décider : `Report.job_ids` peut légitimement référencer des jobs de plusieurs projets différents (rien dans `POST /api/reports` ne restreint la sélection des jobs à un seul projet) — ajouter un `project_id` unique sur `Report` serait sémantiquement incorrect pour un rapport multi-projets, et restreindre la création à un seul projet serait un changement de comportement fonctionnel non demandé par cette phase de hardening. Risque résiduel documenté explicitement (voir [security.md](security.md)), pas une refonte engagée à sa place.

## P3 — frontend, minimal

Uniquement les pages avec un chargement primaire silencieux identifié par l'audit : `projects/index.vue`, `scans/index.vue`, `reports/index.vue`, `projects/[id].vue`, `scans/[id].vue` — `catch` ajouté avec état d'erreur + bouton Retry (idiome déjà utilisé ailleurs dans l'app). `projects/[id].vue` et `scans/[id].vue` ont désormais un `v-else` de secours après leur `v-if="loading"`/`v-else-if="…"`, qui rendait une page blanche pure en cas de panne API. Aucune refonte de composants, aucune factorisation du polling triplé déjà identifié par l'audit, aucun changement de state management, aucune synchronisation d'état dans l'URL — explicitement hors scope de cette phase.

## Vérification réelle (Docker + navigateur)

Conteneurs `cyberlab-api`/`cyberlab-worker`/`cyberlab-frontend` reconstruits. Migration `e5f1a9c7d3b2` appliquée sur la vraie base de dev — backup pris avant, cycle upgrade → downgrade (jusqu'à `6ad0daaf9daa`, traversant le downgrade corrigé de `6495416ebbf2`) → upgrade vérifié deux fois, données réelles (28 jobs / 2 projects / 1 asset) confirmées intactes après.

- `/docs`/`/openapi.json` : 401 sans token, 200 avec token (header ou `?token=`), `/api/health`/`/api/jobs` inchangés.
- Target texte libre non reconnue (`scanme.nmap.org`) → 403 réel. Target texte libre reconnue (`cyberlab-kali`) → 201 puis exécution réelle réussie (vrai nmap via l'agent Kali, `SUCCESS`, XML nmap authentique dans `stdout`).
- Asset enregistré non autorisé (`UNKNOWN`) → 403 réel sur `POST /api/jobs` avec `target_id`.
- Réconciliation : un Job `QUEUED` délibérément orphelin (créé directement dans le conteneur worker réel, `created_at` antidaté d'1h) a été correctement résolu en `FAILED` par la vraie fonction `reconcile_stuck_jobs()`.
- Génération de rapport (`POST /api/reports`) toujours fonctionnelle après tous les changements.
- Navigation réelle au navigateur : `/projects`, `/scans`, `/scans/{id}`, `/reports` — tous rendus correctement avec des données réelles, y compris les nouveaux chemins de gestion d'erreur (non déclenchés sur le chemin heureux, comme attendu).
- AI Memory concurrency et rate limiting : couverts par de vrais tests d'intégration contre le vrai Postgres/Redis (pas de mocks) déjà exécutés dans la suite automatisée — non re-démontrés séparément en direct dans Docker, cette couverture étant jugée suffisante.

## Tests

41 nouveaux tests backend (623 au total) : 8 pour la protection `/docs` (matrice complète auth on/off × token présent/absent/query), 8 pour le bypass target texte libre (matrice complète + révocation mi-vol), 6 pour la concurrence AI Memory (dont le test à 2 threads synchronisés par `threading.Barrier`), 6 pour la réconciliation, 5 pour le rate limiting, plus les fixtures de test durcies. 0 nouveau test frontend requis — le hardening cible des chemins déjà couverts par les 125 tests existants ; typecheck frontend inchangé (les 26 erreurs pré-existantes dans `tools/index.vue`, déjà tracées comme réellement inertes lors de l'audit global, ne sont pas touchées par cette phase).

## Ce qui n'a délibérément pas été fait

- Pas de fusion Mission/Chain, malgré la duplication structurelle documentée par l'audit global — hors scope explicite de cette phase.
- Pas de refonte du scoping des rapports — analysé, documenté comme risque résiduel accepté.
- Pas de RBAC/multi-utilisateur — décision déjà assumée depuis la Phase 11, non remise en cause ici.
- Pas de refonte frontend — uniquement les 5 pages avec un chargement primaire silencieux identifié par l'audit.
- Pas de redaction de secrets dans stdout/stderr des outils, pas de headers de sécurité (CSP, etc.) — findings LOW/INFO de l'audit global, non traités dans cette passe de hardening P0-P3.
