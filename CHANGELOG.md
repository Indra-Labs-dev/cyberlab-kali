# Changelog

## Unreleased — Phase 22 — Reports 2.0 & Pentest Workspace

Dernière phase de la roadmap actuelle. Deux volets additifs, aucune réécriture de moteur existant. Voir [docs/phase-22-reports-2-pentest-workspace.md](docs/phase-22-reports-2-pentest-workspace.md) pour l'architecture complète.

- **`ReportTemplate`** (`executive`/`technical`/`evidence_package`) au-dessus du
  moteur de rendu Phase 9 inchangé — `Report.template`, orthogonal au
  `format` déjà existant. `technical` (défaut) reproduit exactement le
  contenu déjà livré, vérifié octet-à-octet non régressif. `executive`
  retire description/recommandation par finding et toute la section
  Timeline & AI Analysis. `evidence_package` surface pour la première fois
  `finding.evidence` (existait déjà dans `build_report_data()` depuis la
  Phase 9, jamais rendu avant cette phase) et `Job.evidence_sha256`
  (Phase 20, désormais inclus dans le dict du builder -- seul ajout
  additif au builder lui-même). JSON ignore délibérément `template`
  (export à fidélité complète, pas une vue).
- **`app/reports/builder.py::build_report_data()`** : un seul champ ajouté
  (`evidence_sha256` par job), aucun champ retiré ni renommé.
- **Onglet Notes** sur la page Project (`Project.notes`, texte libre) --
  seul manque réel identifié dans le "Pentest Workspace" du brouillon
  original, la timeline demandée était déjà livrée par la Phase 20.
  Aucune nouvelle route : `PATCH /api/projects/{id}` était déjà générique
  depuis la Phase 11, `notes` y transite automatiquement une fois ajouté
  au schéma.
- Migration `d4f6b1e8c9a7` (colonnes `reports.template` et
  `projects.notes`). 34 nouveaux tests backend (593 au total, dont les
  toutes premières routes `/api/reports` testées au niveau HTTP), 2
  nouveaux tests frontend (125 au total).
- Vérifié en conditions réelles (Docker + navigateur) : rapport Evidence
  Package généré contre un job réel affichant le vrai hash et la vraie
  evidence, rapport Executive confirmé sans description ni timeline,
  notes de projet confirmées persistantes après rechargement complet de
  la page.

## Unreleased — Phase 21 — Tool Orchestrator (chaînage de jobs)

Chaînage **déterministe** de jobs (`nmap` → `whatweb` → `nuclei`, chaque
étape gardée par une condition simple sur le résultat de la précédente),
entièrement séparé de la Phase 18 (Agents IA) -- rappel explicite déjà
donné pendant la conception de la Phase 18 : "Ne pas confondre le futur
orchestrateur IA de Phase 18 avec le Tool Orchestrator de Phase 21." Voir
[docs/phase-21-tool-orchestrator.md](docs/phase-21-tool-orchestrator.md)
pour l'architecture complète.

- **`MissionTemplate`/`MissionTemplateStep`** (définition, réutilisable,
  aucune IA) + **`ChainRun`/`ChainRunStep`** (une exécution réelle contre
  un Asset précis, étapes copiées du template à la création -- jamais une
  référence vivante, même précédent que `MissionStep`, Phase 18).
  Démarrer un run est déjà l'action délibérée de l'humain : pas d'étape
  DRAFT/APPROVED séparée, contrairement à la Mission IA de la Phase 18
  (qui doit réviser un plan proposé par un modèle).
- **`advance_chain_run()`** (`backend/app/chains/service.py`) est le 4ᵉ
  appelant indépendant de `is_executable()` + `prepare_job()` dans ce
  projet -- après `POST /api/jobs`, le ticker Phase 14, et
  l'orchestrateur Mission Phase 18. Jamais un chemin d'exécution
  parallèle : `app/jobs/service.py` et `app/api/routes/jobs.py` non
  modifiés par cette phase.
- **Isolation** : avancer une chaîne crée un nouveau `Job` -- la même
  catégorie de risque que l'avancement de Mission (Phase 18), donc le
  même patron d'isolation (hook dans le `finally` le plus externe
  d'`execute_job()`, session séparée, ne peut jamais affecter
  `job.status`) -- **pas** le patron inline du hash de la Phase 20
  (calcul local sans création de Job).
- **3 conditions, aucun DSL** (`backend/app/chains/conditions.py`) :
  `PORT_OPEN` (résultat nmap), `TECHNOLOGY_DETECTED` (réutilise
  `technologies_from_whatweb()`, Phase 13/14, telle quelle), `MIN_SEVERITY`
  (résultat nuclei, table de rang dédiée sur les sévérités minuscules).
  Cas spécial étroit et documenté comme tel : auto-injection des `tags`
  nuclei depuis les technologies détectées par whatweb (assainies contre
  le pattern réel de l'argument, jamais un mécanisme de templating
  général).
- **Divergence documentée** : une condition non remplie marque l'étape
  `SKIPPED` et le run **`COMPLETED`** (arrêt normal et attendu d'un
  pipeline conditionnel) -- délibérément différent du `SKIPPED` de la
  Phase 18, toujours `FAILED` (toujours une autorisation révoquée ou une
  erreur d'outil, toujours préoccupant). Autorisation révoquée ou outil
  invalide restent `FAILED` ici aussi.
- **Concurrence** : verrouillage bloquant `SELECT ... FOR UPDATE` (pas
  `SKIP LOCKED`), même patron que la Phase 18, prouvé avec deux vrais
  threads/deux vraies sessions PostgreSQL : exactement un `Job` créé pour
  une même étape.
- **API** : `POST/GET/DELETE /api/chains/templates`, `POST/GET
  /api/chains/runs`, `GET /api/chains/runs/{id}`, `POST
  /api/chains/runs/{id}/cancel`. Validation à la création d'un template :
  outil/profil réellement enregistrés (Tool Registry), première étape
  obligatoirement `ALWAYS`. Supprimer un template ne détruit jamais
  l'historique de ses runs (`ON DELETE SET NULL`, étapes déjà copiées).
- **Frontend** : nouvelle page `/chains` (gestion des templates) et
  nouvelle section "Tool Orchestrator" sur la page Asset
  (`AssetChainRun.vue`) -- démarrage immédiat, polling borné (même
  idiome que `/ai/missions`), badges dédiés
  (`ChainRunStatusBadge`/`ChainRunStepStatusBadge`) délibérément non
  partagés avec ceux de la Phase 18.
- **Sécurité** : 5 nouvelles routes ajoutées à
  `test_every_api_route_is_guarded_when_auth_enabled`. Détail complet
  dans docs/security.md.
- **Bug réel trouvé pendant la vérification** : dans la fixture de test
  elle-même (un Asset inséré directement en base sans passer par
  `infer_default_authorization()` restait `UNKNOWN` au lieu de `LAB`),
  pas dans le code de production -- corrigé dans le test uniquement.
- **Migration** : additive uniquement (4 nouvelles tables). Vrai backup
  pris avant tout changement ; upgrade → vérifié → downgrade → vérifié →
  upgrade, exécuté contre la vraie base de dev.
- **Full pipeline vérifié contre le vrai stack Docker** : template réel
  créé via l'UI (`nmap quick_scan` → `whatweb`, condition `PORT_OPEN` sur
  `[80, 443]`), lancé contre l'Asset DVWA réel → run démarré
  immédiatement (`RUNNING`) → `nmap` exécuté réellement par le worker
  RQ/l'agent Kali → condition évaluée contre le **vrai** résultat nmap
  parsé (port non trouvé ouvert dans ce scan réel) → étape 2
  correctement `SKIPPED` (`condition not met: PORT_OPEN`) → run
  correctement `COMPLETED` (pas `FAILED`) -- la sémantique "arrêt normal"
  fonctionne en conditions réelles, pas seulement en test. Le hook
  Mémoire IA (Phase 19) a échoué en parallèle (Ollama injoignable) sans
  aucun effet sur le Job ni sur le run -- preuve supplémentaire en
  conditions réelles de l'indépendance des hooks. 67 nouveaux tests
  backend (559 au total), 28 nouveaux tests frontend (123 au total).
- See [docs/phase-21-tool-orchestrator.md](docs/phase-21-tool-orchestrator.md)
  for the full architecture, audit, and verification log.

## Unreleased — Phase 20 — Evidence & Chain of Custody

Hash SHA-256 du `stdout` de chaque `Job` (preuve d'intégrité minimale, pas
de vault cryptographique) et Evidence Timeline par Asset/Project (fusion
chronologique de `Job`/`Finding` déjà existants, pas une nouvelle table).
Voir [docs/phase-20-evidence-chain-of-custody.md](docs/phase-20-evidence-chain-of-custody.md)
pour l'architecture complète.

- **`Job.evidence_sha256`** (`String(64)`, nullable — même forme que
  `Finding.signature`, migration `b2d5f8a1c6e3`) : calculé **inline** dans
  `app/jobs/tasks.py::_execute_job`, dans la même transaction que
  `exit_code`/`result` — pas un hook isolé comme l'avancement de Mission
  ou la régénération de mémoire (Phase 18/19), qui sont isolés *parce que*
  ce sont des appels réseau/LLM lents ; un SHA-256 local est instantané.
- Calculé pour **tout** job ayant produit un `stdout`, y compris les jobs
  `FAILED` par code de sortie non nul (pas seulement les `SUCCESS`) — un
  `stdout` vide obtient un hash bien défini, jamais confondu avec `NULL`.
  `NULL` seulement quand l'outil n'a jamais tourné (les deux chemins
  d'exception existants ne posent jamais `job.stdout`).
- **`JobResponse.evidence_sha256`** — un seul champ de schéma ajouté,
  aucune nouvelle route : déjà exposé automatiquement sur `GET
  /api/jobs`, `GET /api/jobs/{id}`.
- **`EvidenceTimeline.vue`** (nouveau composant partagé, frontend) : fusion
  purement présentationnelle de `jobs`+`findings` déjà chargés par la page
  parente (aucun appel réseau propre), triée chronologiquement (Job :
  `finished_at ?? created_at` ; Finding : `first_seen`). Utilisé comme
  nouvelle section sur `pages/assets/[id].vue` et nouvel onglet `timeline`
  sur `pages/projects/[id].vue` — jamais fusionné avec
  `AssetChangeTimeline.vue` (Phase 14, hors périmètre littéral de cette
  phase, composant déjà livré non retouché).
- **Hash affiché** sur `pages/scans/[id].vue`, à côté du `stdout`, avec
  copie en un clic.
- **Bug préexistant trouvé et corrigé** (sans rapport avec cette phase) :
  `JobStatusBadge.vue` utilisait `computed()` sans l'importer
  explicitement — fonctionnait dans l'app Nuxt réelle (auto-import), mais
  plantait dans tout test Vitest simple le montant pour la première fois
  (découvert en testant `EvidenceTimeline.vue`, qui l'utilise). Corrigé,
  même classe de correction déjà appliquée aux badges de la Phase 18.
- **Migration** : additive uniquement (une colonne). Vrai backup pris
  avant tout changement ; upgrade → vérifié → downgrade → vérifié →
  upgrade, exécuté contre la vraie base de dev.
- **Full pipeline vérifié contre le vrai stack Docker** : conteneurs
  reconstruits et redémarrés. Scan `whatweb` réel lancé depuis l'UI contre
  l'Asset DVWA réel → hash affiché sur la page Scan → **recalculé
  indépendamment côté PostgreSQL** (`encode(sha256(stdout::bytea),
  'hex')`) → correspondance exacte, preuve cryptographique que le hash
  stocké est correct. Evidence Timeline vérifiée sur les deux pages
  (Asset et Project), correctement entrelacée par ordre chronologique.
  Un job antérieur à cette phase confirmé sans hash (comportement
  attendu, pas de recalcul rétroactif). Logs worker : une régénération de
  résumé IA (Phase 19) a échoué en conditions réelles pendant ce test
  (Ollama momentanément injoignable) sans jamais faire échouer le Job
  lui-même — confirmation en production, pas seulement en test, que
  l'isolation Phase 19 fonctionne. 11 nouveaux tests backend (497 au
  total), 6 nouveaux tests frontend (101 au total).
- See [docs/phase-20-evidence-chain-of-custody.md](docs/phase-20-evidence-chain-of-custody.md)
  for the full architecture, audit, and verification log.

## Unreleased — Phase 19 — Mémoire IA par Projet/Asset

Résumé de projet stocké (régénéré après l'activité de scan, jamais
recalculé à chaque consultation) et questions temporelles répondues en
enrichissant le chat existant des données déjà structurées du Diff Engine
(Phase 14) — jamais un nouveau système de stockage. Voir
[docs/phase-19-ai-memory.md](docs/phase-19-ai-memory.md) pour
l'architecture complète.

- **Table dédiée `project_ai_summaries`, pas un `Finding` de type
  `SUMMARY`** : la roadmap laissait les deux options ouvertes ; `Finding`
  n'a aucune colonne discriminante et son schéma entier est structuré
  autour d'une vulnérabilité (severity/CVE/risk score/lifecycle) — une
  table dédiée (`backend/app/models/project_ai_summary.py`, migration
  `a1c4e6f9b3d2`) suit le précédent de chaque phase précédente (`Mission`,
  `GraphEdge`, `VulnerabilityIntel`).
- **`SummaryAgent`** (`backend/app/ai/agents/summary.py`, lecture seule --
  aucun accès `Session`) : écrit un résumé texte libre à partir des
  Assets/répartition de sévérité/derniers `AssetChangeEvent` déjà chargés
  -- jamais de requête DB, jamais d'écriture, comme le Correlation/Report
  Agent (Phase 18).
- **Régénération isolée** (`backend/app/ai/memory.py`,
  `regenerate_project_summary()`/`regenerate_project_summary_for_job()`,
  sync, module-level) : hook dans le `finally` le plus externe
  d'`execute_job()` -- même patron d'isolation que l'avancement de
  Mission (Phase 18), jamais dans la même transaction que Diff
  Engine/Correlation/Graph (un appel IA est trop lent/réseau pour
  partager leur commit). Cooldown de 5 minutes (`_REGEN_COOLDOWN`)
  approxime "après chaque batch de scans" sans nouvelle infrastructure de
  batch ; la régénération manuelle le contourne.
- **Chat enrichi** : `ChatRequest.project_id` (nouveau, optionnel) injecte
  le résumé stocké + les 20 derniers `AssetChangeEvent` du projet dans le
  system prompt -- le chat reste strictement single-turn, aucun historique
  de conversation persisté (`AIConversation`/`AIMessage` reste hors de la
  définition officielle de cette phase).
- **API** : `GET /api/ai/projects/{id}/summary` (`404` tant qu'aucun
  résumé n'a jamais été généré), `POST
  /api/ai/projects/{id}/summary/regenerate` (contourne le cooldown).
- **Frontend** : remplace le stub de l'onglet `ai` sur
  `pages/projects/[id].vue` par une carte résumé (horodatage, bouton
  Regenerate, état vide) et une mini Q&A à un seul tour ("Ask about this
  project"), grounded sur le résumé + les changements récents. Chargement
  paresseux -- le résumé n'est récupéré qu'à la première ouverture de
  l'onglet.
- **Bug réel trouvé et corrigé pendant la vérification** : un simple
  `asyncio.run()` pour ponter l'appel IA async depuis le hook sync échoue
  silencieusement (absorbé par le `except Exception` d'`execute_job()`) si
  une boucle asyncio est déjà active dans le thread appelant -- n'affecte
  jamais la production réelle (le worker RQ n'a pas de boucle active),
  mais affectait silencieusement plusieurs tests préexistants
  (`tests/assets/test_activity.py`, entre autres) qui appellent
  `execute_job()` depuis une fonction de test `async def`. Corrigé par
  `_run_coro()` (bascule vers un thread avec sa propre boucle si
  nécessaire), prouvé par un test dédié appelé depuis une vraie boucle
  asyncio active, et confirmé par la disparition des `RuntimeWarning:
  coroutine ... was never awaited` sur la suite complète.
- **Migration** : additive uniquement (une nouvelle table). Vrai backup
  pris avant tout changement ; upgrade → vérifié → downgrade → vérifié →
  upgrade, exécuté contre la vraie base de dev.
- **Full pipeline vérifié contre le vrai stack Docker** : conteneurs
  `cyberlab-api`/`cyberlab-worker`/`cyberlab-frontend` reconstruits et
  redémarrés. Sur un projet réel (21 findings informationnels réels,
  changements réels de Phase 16) : `GET /summary` → `404` correctement
  affiché comme état vide → `Regenerate` → appel réel à Ollama
  (`qwen2.5-coder:3b`) → résumé **factuellement exact** (criticité,
  décompte de findings, changements récents tous corrects, rien
  d'inventé) → "Ask about this project" → réponse **grounded** citant
  exactement le dernier `AssetChangeEvent` réel (type, champ, horodatage)
  → logs API propres sur toute la séquence, aucune erreur 500. 28
  nouveaux tests backend (492 au total), 2 nouveaux tests frontend (95 au
  total).
- See [docs/phase-19-ai-memory.md](docs/phase-19-ai-memory.md) for the
  full architecture, audit, and verification log.

## Unreleased — Phase 18 — Agents spécialisés (IA)

Autonomie **Niveau 2 — Execute Approved Tasks** : un humain approuve un
plan entier en une fois, puis chaque étape s'exécute automatiquement,
re-validée individuellement par le Policy Engine avant de partir — jamais
un chemin d'exécution parallèle à `POST /api/jobs`. Niveau 3 non livré
comme autonomie complète (pas d'enchaînement conditionnel entre étapes),
mais ses fondations le sont. Niveau 4 hors scope. Voir
[docs/phase-18-ai-agents.md](docs/phase-18-ai-agents.md) pour
l'architecture complète.

- **Pas de `create_job()` unifié, pas de quatrième mécanisme de création
  de Job** : l'inspection du code réel a montré que le clivage async
  (routes FastAPI)/sync (worker RQ, ticker Phase 14) est déjà une
  décision architecturale assumée (`backend/app/jobs/service.py`).
  `MissionOrchestrator` (`backend/app/ai/orchestrator.py`) devient un
  **troisième** appelant indépendant de `is_executable()` +
  `prepare_job()`, suivant exactement le patron déjà établi par
  `app/scheduling/ticker.py::process_schedule` — `app/jobs/service.py` et
  `app/api/routes/jobs.py` ne sont pas modifiés par cette phase.
- **`Mission`/`MissionStep`** (nouvelles tables, migration
  `f8721b028a2d`) : `create_mission()` (async, réutilise
  `AIMissionPlanner` sans modification) crée un plan `DRAFT` qui ne
  démarre jamais tout seul ; `approve_mission()`/`advance_mission()`/
  `cancel_mission()` (sync, fonctions module-level — pas des méthodes,
  elles n'ont besoin d'aucun provider IA) créent un vrai `Job` par étape,
  revérifient `is_executable()` avant **chaque** étape (jamais seulement
  à l'approbation), et arrêtent la Mission au premier échec (stop-on-
  failure, pas de retry dans cette phase).
- **Verrouillage anti-concurrence réel** : `SELECT ... FOR UPDATE`
  bloquant (pas `SKIP LOCKED`, contrairement au ticker Phase 14 qui
  verrouille un lot de lignes indépendantes/skippables) — un second appel
  concurrent attend, relit l'état déjà à jour, devient un no-op. Prouvé
  avec deux vrais threads/deux vraies sessions PostgreSQL, l'un maintenu
  dans sa transaction pendant que l'autre est vérifié explicitement
  bloqué sur le verrou : exactement un `Job` créé.
- **Isolation Job/Mission dans `execute_job()`** : le hook
  `advance_mission_for_job()` s'exécute dans le `finally` le plus externe
  — après la fermeture de la session du Job et le commit de son statut
  terminal, dans sa propre session isolée, dont les erreurs sont
  journalisées et avalées sans jamais pouvoir réécrire `job.status`.
  Vérifié en forçant une exception dans le hook : le Job reste `SUCCESS`.
- **Correlation Agent** (`backend/app/ai/agents/correlation.py`, lecture
  seule — aucun accès `Session`) : propose des liens entre `Finding` que
  les 3 règles déterministes de la Phase 16 ne couvrent pas. Persistées
  dans une table dédiée (`AICorrelationSuggestion`, `status: PENDING`)
  — jamais directement dans `FindingRelation`, qui reste exclusivement
  écrite par le moteur déterministe. Une suggestion ne devient une
  relation réelle que sur acceptation humaine explicite (`rule:
  RULE_AI_ACCEPTED`, toujours traçable comme d'origine IA), idempotent.
- **Report Agent** (`backend/app/ai/agents/report.py`, lecture seule) :
  ne connaît ni `build_report_data()`, ni `render()`, ni le modèle
  `Report`. Propose un titre + une liste de scans (`ReportProposal`) ;
  la génération réelle reste exclusivement `POST /api/reports`, **le même
  endpoint inchangé** que la création manuelle.
- **API** : `POST/GET /api/ai/missions`, `GET /api/ai/missions/{id}`,
  `POST /api/ai/missions/{id}/{approve,cancel}`, `POST/GET
  /api/ai/correlation-suggestions`, `POST
  /api/ai/correlation-suggestions/{id}/{accept,dismiss}`, `POST
  /api/ai/reports/propose` — `/plan`, `/analyze/{job_id}`, `/chat`
  inchangées.
- **Frontend** : nouvelle page `/ai/missions` (distincte du Mission
  Planner existant sur `/ai`, qui reste inchangé) — création/liste de
  Missions avec les 6 statuts (`MissionStatusBadge`), étapes
  (`MissionStepStatusBadge`), Approve/Cancel, polling borné pendant
  `RUNNING` ; Correlation Suggestions avec étiquette **"Suggestion IA"**
  visuellement distincte des relations déterministes, Accept/Reject ;
  Report Proposal avec titre/liste de scans éditables avant `Generate`.
- **Sécurité** : garde-fous statiques existants
  (`test_ai_module_has_no_write_access_to_target_model`,
  `test_ai_module_has_no_subprocess_or_docker_access`) étendus en
  `rglob` récursif pour couvrir `orchestrator.py`/`agents/*.py`, ajoutés
  par cette phase ; nouveau garde-fou statique confirmant qu'aucun agent
  n'a d'accès `Session`. 9 nouvelles routes ajoutées à
  `test_every_api_route_is_guarded_when_auth_enabled`. Détail complet
  dans docs/security.md.
- **Bug réel trouvé et corrigé pendant la vérification** : le premier jet
  d'`advance_mission()` marquait une étape sans outil valide (halluciné
  ou rejeté par `prepare_job()`) comme `FAILED` — violant la contrainte
  DB `ck_mission_step_job_id_required_when_executed`, qui exige un
  `job_id` pour ce statut puisqu'aucun `Job` n'a jamais existé pour cette
  étape. Corrigé avec `SKIPPED` (la sémantique correcte). Trouvé par un
  test échouant avec une vraie `IntegrityError` PostgreSQL au premier
  lancement, pas en relecture de code.
- **Migration** : additive uniquement (3 nouvelles tables). Vrai backup
  pris avant tout changement ; upgrade → vérifié → downgrade → vérifié →
  upgrade, exécuté contre la vraie base de dev.
- **Full pipeline vérifié contre le vrai stack Docker** : conteneurs
  `cyberlab-api`/`cyberlab-worker`/`cyberlab-frontend` reconstruits et
  redémarrés. Mission créée avec un objectif en langage naturel contre
  l'Asset DVWA réel et Ollama réel (`qwen2.5-coder:3b`) → 6 étapes
  réelles proposées → Approve → premier `Job` (`amass`) créé, enfilé,
  repris par le vrai worker RQ, appel réel à l'agent Kali (`200 OK`) →
  `Job` `FAILED` (un vrai résultat d'outil : erreur `sudo`/conteneur non
  liée à cette phase, pas une simulation) → l'étape correctement
  réconciliée en `FAILED`, la Mission arrêtée, les 5 étapes suivantes
  laissées `PENDING` sans y toucher. Report Proposal généré par le
  modèle pour un projet réel, édité, `Generate` → rapport réellement créé
  via `POST /api/reports` et visible dans "Past reports" au même titre
  qu'un rapport manuel. 58 nouveaux tests backend (456 au total), 25
  nouveaux tests frontend (93 au total).
- See [docs/phase-18-ai-agents.md](docs/phase-18-ai-agents.md) for the
  full architecture, audit, and verification log.

## Unreleased — Cross-cutting — Frontend Architecture & UX (18a–18e)

Frontend-only consolidation pass, run between the official Phase 17
(Security Graph) and Phase 18 (specialized AI agents) of
[docs/roadmap.md](docs/roadmap.md) — **not itself a numbered roadmap
phase**. Addresses architectural/UX debt that had accumulated across
Phases 13–17 (local color-maps, ad-hoc loading/empty states, flat
navigation, an 895-line Asset detail page) before AI agents add more
surface to the frontend. No backend, API, or database change in any of
18a–18e, and no AI-agent code — the official Phase 18 has not started.

- **18a — Foundations**: shared TypeScript types mirroring backend schemas
  field-for-field (`Asset`, `Finding`, `Project`, `GraphNode`/`GraphEdge`,
  `RiskSummary`), centralized design-system color maps
  (`app/constants/colors.ts` — severity / risk-priority / criticality /
  authorization / finding-status / tool-risk-level kept as five
  deliberately separate domains, never merged), `Badge` + domain badges
  (`SeverityBadge`/`RiskBadge`/`StatusBadge`/`CriticalityBadge`/
  `AuthorizationBadge`), `LoadingState`/`EmptyState`, `useAssets()`/
  `useProjects()` composables, Vitest set up from scratch (plain
  `@vitejs/plugin-vue` + `happy-dom`, no `@nuxt/test-utils`).
- **18b — Navigation**: hierarchical sidebar (Attack Surface vs Execution &
  Support), `/targets` renamed to `/assets` with legacy `/targets` and
  `/targets/:id` kept as native vue-router redirects
  (`definePageMeta({ redirect })`) — bookmarks and old links keep working.
  Section-aware active-route matching (`app/utils/navigation.ts`),
  accessible mobile drawer (Escape, backdrop, focus-visible), `aria-current`
  on the active nav item.
- **18c — Graph & Intelligence**: `/graph` (global Security Graph entry
  point with search-by-asset/finding/CVE/service/technology) and
  `/intelligence` (EPSS/CISA KEV/NVD sync status, CVE→Findings
  cross-search) as real pages, replacing the "Soon" placeholders from 18b.
  `SecurityGraph.vue` reused unmodified except for a CVE-detail side panel
  and a real mobile-overflow fix (canvas collapsing to ~2px height in the
  `flex-col` layout).
- **18d — Asset page decomposition**: `pages/assets/[id].vue` reduced from
  895 to 275 lines by extracting `AssetHeader`, `AssetContinuousRecon`,
  `AssetChangeTimeline`, `AssetRiskOverview`, `AssetFindingsList` into
  `app/components/asset/`. Single source of truth kept in the parent page
  (`asset`/`jobs`/`findings`/`tools`); cross-section refresh (schedule
  "Run now" → parent's `loadAll()`) passed as an async function prop, not
  duplicated state.
- **18e — Consolidation**: audited and fixed color-map duplication that had
  escaped 18a/18d in four files (`AssetHeader.vue`, `scans/[id].vue`,
  `projects/[id].vue`, `tools/index.vue` — all swapped to the centralized
  constants, zero domain merges); migrated the four Asset section
  components to `LoadingState`/`EmptyState`; fixed two icon-only buttons
  missing `aria-label` (`SecurityGraph.vue`'s panel-close button, the Asset
  tag-remove button) and one unlabeled input; corrected "targets" →
  "assets" wording in UI-visible labels (`projects/index.vue`,
  `projects/[id].vue`, `tools/index.vue`) while leaving backend field
  names, Cytoscape's own vocabulary, and the legacy redirects untouched;
  removed `ComingSoon.vue` (confirmed zero references anywhere in `app/`).
- **Tests**: 68 tests green across 15 files (Badge/SeverityBadge/RiskBadge/
  StatusBadge, GraphSearchBar, CveDetailPanel, IntelligenceSyncStatus, the
  five Asset section components, `useAssets`/`useProjects`/`useGraph`,
  color-map and navigation-logic unit tests).
- **Build/typecheck**: `npm run build` green; `npm run typecheck` reports
  exactly the 26 pre-existing errors in `app/pages/tools/index.vue`
  (`runState[tool.name]` possibly-undefined), confirmed identical to the
  pre-18a baseline via a `git stash` comparison — pre-existing debt, not
  introduced or hidden by this work, deliberately left unfixed per its own
  explicit scope.
- **Docker**: `cyberlab-frontend` rebuilt and restarted after every
  sub-phase, never a single rebuild at the end.
- **Browser verification**: real, repeated passes against the actual
  Docker stack (not mocks) covering every route (`/`, `/projects`,
  `/projects/:id`, `/assets`, `/assets/:id`, `/findings`, `/findings/:id`,
  `/graph`, `/intelligence`, `/tools`, `/scans`, `/scans/:id`, `/terminal`,
  `/labs`, `/ai`, `/reports`, `/settings`), desktop and mobile (375px)
  viewports, the legacy `/targets` and `/targets/:id` redirects, and
  end-to-end interactions against real backend data (tag add/remove,
  schedule create/run-now/delete with confirmed cross-section refresh, AI
  risk-analysis trigger, intel sync trigger with real EPSS/KEV network
  calls).
- **Explicitly does not touch**: backend, API contracts, database schema,
  or the official Phase 18 (specialized AI agents) — no agent code exists
  yet; see [docs/roadmap.md](docs/roadmap.md) for that phase's actual
  scope.

## Unreleased — Phase 17 — Security Graph

- **PostgreSQL only, no graph database**: a single `graph_edges` table
  (`backend/app/models/graph_edge.py`) — no Neo4j, no new microservice, at
  CyberLab's current scale (hundreds of edges per Asset) a recursive CTE
  over an indexed table is simple and stays transactionally consistent
  with the rest of the system.
- **5 node types** (`ASSET`, `FINDING`, `CVE`, `SERVICE`, `TECHNOLOGY`),
  no more. `ASSET`/`FINDING` reference real rows; `CVE`/`SERVICE`/
  `TECHNOLOGY` are virtual nodes identified by a natural key
  (`CVE-2021-44228`, `80/tcp`, `Apache`) — no local CVE/Service/Technology
  table created just to satisfy the graph model.
- **5 fixed edge rules, not a rule engine** (`backend/app/graph/builder.py`):
  `HAS_FINDING`, `EXPOSES` (nmap/masscan open ports only — whatweb/nuclei
  never produce one, they observe an application, not a confirmed port),
  `USES_TECHNOLOGY` (from `Asset.technologies`, already real data since
  Phase 13, never re-derived), `REFERENCES_CVE` (from `Finding.cve_ids`),
  `RELATED_TO` (Finding↔Finding mirrors Phase 16's `FindingRelation`
  verbatim; Asset↔Asset only for two assets in the *same* project sharing
  an observed technology — the only Asset-Asset relationship honestly
  derivable from current data). Every edge carries a human-readable
  `reason` — never a silent guess.
- **Idempotent by construction**: `INSERT ... ON CONFLICT (from_type,
  from_id, to_type, to_id, relation) DO UPDATE`, atomic in one statement —
  simpler than Phase 16's Finding upsert on purpose, since an edge carries
  no accumulated state to merge. Verified real: 42 edges before/after a
  full rebuild, before/after a repeat scan, before/after `docker compose
  restart cyberlab-worker`, zero duplicates found by an explicit `GROUP BY
  ... HAVING count(*) > 1` check.
- **Depth-limited, cycle-safe traversal** (`backend/app/graph/queries.py`):
  a single `WITH RECURSIVE` CTE, bidirectional walk with a `visited` array
  guarding against cycles, `MAX_GRAPH_DEPTH = 3` enforced server-side
  regardless of what a caller requests. Verified against a real 3-node
  cycle (`A → B → C → A`, an actual case the Asset↔Asset rule can produce)
  — terminates in ~46ms instead of looping forever.
- **New API**: `GET /api/graph/{assets,findings,nodes,projects}/...` (depth
  query param, `404` for an unknown real node, never `404` for an unknown
  virtual one — an empty graph is the honest answer) and `POST
  /api/graph/rebuild` (queued via the existing RQ queue, same pattern as
  the Phase 15 intelligence sync trigger — never inline in the request,
  and RQ's one-job-at-a-time processing serializes concurrent rebuilds for
  free).
- **Frontend**: `SecurityGraph.vue`, the first graph-visualization
  dependency in the project (Cytoscape.js — no existing library covered
  this, dynamically imported the same way `@xterm/xterm` already is on
  the Terminal page). Zoom/pan/select, type filters, text search, depth
  1/2/3, Fit/Reset — clicking a node opens a side panel with its real
  metadata and every connection's relation + human-readable reason, with
  a link to the node's actual CyberLab page. Added as a new section on
  `/targets/[id]` and a new tab on `/projects/[id]` — no existing page
  content replaced.
- **Security audit**: IDOR/cross-project leakage, SQL injection via
  `node_id`, negative/zero/oversized depth, recursive-cycle DoS, XSS via
  labels/reason, mass assignment, unauthenticated rebuild — all verified,
  see docs/security.md. The Asset↔Asset rule's same-project scoping
  double as the cross-project leakage protection: two assets in different
  projects can never be linked, so a traversal can never cross a project
  boundary through it (verified:
  `test_build_graph_never_links_assets_across_different_projects`).
- **Migration**: additive only (one new table). Real backup taken before
  any change; upgrade → verified → downgrade → verified → upgrade, all
  run against the real dev database before any data existed in
  `graph_edges` (the graph being reconstructible at any time from existing
  Findings/Assets, no historical edge is fabricated).
- **Full pipeline verified against the real Docker stack**: the DVWA
  Asset from Phase 16's E2E reused, graph built directly against real
  PostgreSQL (42 correct edges on the first attempt), verified again via
  the real API and in a real browser (graph rendered on both the Asset and
  Project pages, node clicks opening the side panel with real connections,
  depth selector working, zero console errors), `POST /api/graph/rebuild`
  confirmed processed by the real RQ worker in its logs. 39 new tests, 406
  total green (367 pre-existing + 39 new).
- **Known limitation, honestly reported rather than simulated**: the
  `REFERENCES_CVE` rule is verified by a real-database unit test but not
  by a fresh live nuclei scan against DVWA in this phase, since the
  Phase 15 test template that produced a genuine CVE match was
  deliberately removed from the Kali container after that phase's own
  verification, and no template currently loaded reliably produces a CVE
  against a stock DVWA container.
- See [docs/phase-17-security-graph.md](docs/phase-17-security-graph.md)
  for the full architecture, audit, and verification log.

## Unreleased — Phase 16 — Correlation, Deduplication & Finding Lifecycle

- **Deduplication signature** (`backend/app/findings/signature.py`): pure,
  deterministic SHA-256 identity — `(asset_id, sorted CVE ids)` when the
  finding carries a CVE (tool-independent on purpose, so two different
  tools reporting the same CVE on the same asset merge into one Finding),
  else `(asset_id, normalized title, port, protocol)`. `source_tool` is
  never part of the identity key. A finding whose Job has no `target_id`
  (free-text target, no Asset) gets `signature=NULL` and stays entirely
  outside dedup/lifecycle/correlation — same precedent as the Diff Engine
  (Phase 14) and Risk Score (Phase 15).
- **Race-safe upsert** (`backend/app/findings/service.py::upsert_finding`):
  `SELECT ... FOR UPDATE` plus a SAVEPOINT-isolated speculative INSERT,
  retried on a unique-constraint collision — relies on PostgreSQL itself
  (partial unique index `uq_findings_signature`), not an application-level
  lock. A known value is never overwritten by an unknown one on merge
  (`recommendation`/`description`/`cve_ids`); `first_seen` never regresses,
  `last_seen` always advances, `observation_count` increments,
  `source_tools`/`observation_job_ids` grow without duplicates or loss.
  Proven with two real concurrent PostgreSQL sessions racing on the same
  signature (`tests/findings/test_concurrency.py`) — exactly one Finding,
  rerun 5 times without failure.
- **Finding lifecycle** (`backend/app/findings/lifecycle.py`): fixed
  transition table (`NEW → CONFIRMED → IN_REVIEW → {ACCEPTED_RISK,
  FALSE_POSITIVE, REMEDIATED}`, with `REOPENED` resuming the review flow),
  append-only `finding_status_history`. A matching re-observation
  auto-reopens `REMEDIATED`/`FALSE_POSITIVE` findings — **never**
  `ACCEPTED_RISK` (a conscious human decision must not be silently
  overridden) and never auto-`CONFIRMED`. Verified live against the real
  Docker stack, not just unit tests: full manual lifecycle via the browser
  UI, `FALSE_POSITIVE` → real re-scan → `REOPENED` with correct history,
  `ACCEPTED_RISK` → three real re-scans → status unchanged each time.
- **Correlation, not a rule engine** (`backend/app/findings/correlation.py`):
  exactly 3 fixed rules (`RULE_NMAP_WHATWEB_PORT`, `RULE_NMAP_NUCLEI_PORT`,
  `RULE_SHARED_TECHNOLOGY`), scoped to one Asset's findings, each producing
  a human-readable `reason` — never an opaque link. Idempotent (canonical
  UUID ordering + unique constraint on `(finding_id, related_finding_id,
  rule)`), verified by re-running correlation on the same findings twice
  with zero new relations on the second pass.
- **Real bug found and fixed during E2E verification**: the whatweb/nuclei
  extractors (`backend/app/findings/extractor.py`) stored the Job's generic
  target string on each Finding instead of the per-result resolved URL
  already present in the parsed output — `extract_port_protocol` could
  therefore never derive a port for either tool, silently preventing
  `RULE_NMAP_WHATWEB_PORT`/`RULE_NMAP_NUCLEI_PORT` from ever matching in
  production. Reproduced against the real DVWA lab (zero relations despite
  a matching open port), fixed by using the already-available per-result
  URL, rebuilt/redeployed, re-verified: 10 real relations created.
- **Two more real bugs found while writing the test suite** (see
  [docs/phase-16-correlation-deduplication.md](docs/phase-16-correlation-deduplication.md)):
  `upsert_finding()` crashed for any target-less finding (missing `flush()`
  before a column default was read); the partial unique index enforcing
  the whole concurrency-safety design existed only in the Alembic
  migration, not the SQLAlchemy model — invisible to
  `Base.metadata.create_all()`, so the test database silently lacked the
  very constraint `test_concurrency.py` exists to prove. Both fixed and
  reverified.
- **New API**: `GET /api/findings` gained `status`/`source_tool` filters;
  `GET /api/findings/{id}/history` (status change history, most recent
  first); `GET /api/findings/{id}/relations` (normalized so `finding_id`
  in the response always matches the requested ID regardless of storage
  order); `PATCH /api/findings/{id}/status` (`400` on an invalid
  transition, `404` on an unknown finding, every transition — manual or
  automatic — recorded to history).
- **Frontend**: `/findings` and `/findings/[id]` extended, not redesigned —
  status filter, observation-count/source-tools badges, a Lifecycle panel
  (first/last seen, observation count, reporting tools, status-transition
  buttons limited to valid next states, real history), and a Related
  Findings panel (rule + human-readable reason, links to the linked
  Finding). The Security Graph visualization stays explicitly Phase 17.
- **Migration**: additive only — existing findings backfilled with
  `status=NEW`, `first_seen=last_seen=created_at`, `observation_count=1`,
  `source_tools=[source_tool]`; no signature or relation fabricated for
  pre-Phase-16 data since none can be honestly proven from what already
  exists. Verified real upgrade → downgrade → upgrade against a Postgres
  backup before touching the dev database.
- **Full pipeline verified against the real Docker stack**: a real Asset
  linked to the DVWA lab, scanned with real `nmap`+`whatweb`+`nuclei`,
  correlation producing genuine relations, repeat scans deduplicating
  instead of creating rows, the full lifecycle chain exercised through the
  actual browser UI, and `docker compose restart cyberlab-worker` run
  mid-sequence with no duplication/loss/corruption afterward. 367 tests
  green (292 pre-existing + 75 new).
- See [docs/phase-16-correlation-deduplication.md](docs/phase-16-correlation-deduplication.md)
  for the full architecture, signature algorithm, and verification log.

## Unreleased — Phase 15 — Risk Intelligence & Risk Score

- **CVE/CVSS extraction from nuclei** (`backend/app/tools/parsers/nuclei.py`):
  captures `info.classification` (`cve-id`, `cvss-score`, `cvss-metrics`) —
  previously not parsed at all. Real schema verified live against nuclei
  v3.11.0 in `cyberlab-kali` before writing any code (`cve-id` is a
  lowercased array, normalized to uppercase; CVSS version parsed from the
  vector string prefix, e.g. `CVSS:3.1/...`). `Finding` gains `cve_ids`
  (real extracted data) plus a materialized Risk Score cache:
  `cvss_score`/`epss_score`/`kev`/`risk_score`/`risk_priority`/
  `risk_calculated_at`.
- **Local Vulnerability Intelligence** (`backend/app/models/vulnerability_intel.py`):
  `vulnerability_intel` (CVSS+EPSS, scoped to CVEs CyberLab has actually
  encountered — never a bulk NVD/EPSS dump), `cisa_kev_entries` (the full
  CISA KEV catalog, ~1,700 entries, ~1.5MB — a justified complete download
  since CISA publishes no per-CVE query API, unlike EPSS), `intel_sync_state`
  (per-source sync health, distinguishing "confirmed not in KEV" from
  "KEV never synced").
- **Three real external clients** (`backend/app/intel/`): FIRST.org EPSS
  (batched by CVE, 100 per request), CISA KEV (full catalog), NVD CVE API
  2.0 (only for CVEs missing CVSS elsewhere, version-priority
  V40>V31>V30>V2, rate-limited to ~5 req/30s). All three schemas verified
  against the real live APIs during development before writing the
  parsers. Untrusted-input handling throughout: malformed entries are
  skipped individually rather than failing the whole batch, all typed
  exceptions (`EPSSFetchError`/`CisaKevFetchError`/`NVDFetchError`) are
  caught and recorded to `IntelSyncState`, never propagated to crash the
  sync thread.
- **Background sync, not a new service**: `app/intel/sync.py::
  start_intel_sync_thread()` runs as a daemon thread inside the existing
  `cyberlab-worker` process, deliberately **not** reusing the Phase 14
  `ScheduledJob`/ticker model (that's specifically "run a Kali tool
  against an Asset through the Policy Engine" — intelligence ingestion
  isn't a scan, forcing it through that model would need a fake `asset_id`
  and a meaningless authorization re-check). Daily by default; `POST
  /api/intelligence/sync` triggers an immediate cycle via the existing RQ
  queue (`202`, never blocks on network I/O).
- **Risk Calculator** (`backend/app/risk/calculator.py`): pure, deterministic,
  zero I/O, zero LLM. Normalizes CVSS-or-severity-fallback (weight 0.40),
  EPSS (0.35), and KEV (0.25) onto [0,1] and combines them as a weighted
  average of **only the signals actually available** — a missing EPSS or
  unsynced KEV is excluded and the remaining weights renormalized, never
  faked as 0 or 0.5. Asset criticality (×0.85–1.30) and Finding confidence
  (×0.60–1.00) apply as multiplicative context modifiers rather than
  competing terms in the average. Full formula and mathematical
  justification in
  [docs/phase-15-risk-score.md](docs/phase-15-risk-score.md). Verified:
  KEV=true alone never forces a 100 score; LOW confidence structurally
  caps the score even with every other signal maxed; the extreme case
  (CVSS 10 + EPSS 1.0 + KEV + CRITICAL asset + HIGH confidence) stays
  exactly at the 0–100 bound.
- **Materialized, trigger-based recalculation** (`app/risk/service.py`):
  computed at Finding extraction time, after a relevant EPSS/KEV/NVD sync,
  and after `Asset.criticality` changes (`PATCH /api/assets/{id}`,
  dispatched via `asyncio.to_thread` so it never blocks the event loop).
  `GET /api/findings/{id}/risk` recomputes live (pure CPU, no network)
  rather than trusting the cache blindly, guaranteeing full
  reproducibility; list-level sorting/filtering uses the materialized
  columns to stay fast at scale.
- **New API**: `GET /api/findings` gained `priority`/`kev`/
  `min_risk_score` filters and `sort=risk_score_desc|risk_score_asc`;
  `GET /api/findings/{id}/risk` (full breakdown: inputs, per-component
  weights/availability, human-readable explanation); `GET
  /api/assets/{id}/risk-summary` (critical/high/medium/low/informational/
  KEV finding counts, highest risk score); `POST /api/intelligence/sync` +
  `GET /api/intelligence/status`.
- **Frontend**: `/findings` gained a Top Risks panel (score/priority/CVE/
  KEV/EPSS/CVSS at a glance, matching the spec's example format exactly),
  priority/KEV/min-score filters, risk-score sorting. New `/findings/[id]`
  detail page: Risk Analysis (score, CVSS/EPSS/KEV/asset criticality/
  confidence breakdown) + "Why this score?" explanation. `/targets/[id]`
  (Asset page) gained a Risk Overview panel (critical/high/KEV finding
  counts, highest risk score).
- **Real bug found and fixed during E2E verification** (Tool Registry
  behavior from Phase 12, not this phase, but only surfaced here): nuclei's
  default severity profile (`info,low,medium`) silently filters out a
  `-tags`-scoped scan whose only matching template is `critical`,
  producing `[FTL] Could not run nuclei: no templates provided for scan`
  with no findings and no error surfaced anywhere obviously —
  reproduced, documented, worked around by passing `severity: critical`
  explicitly rather than patched silently.
- **Full pipeline verified against the real Docker stack**: a real nuclei
  template referencing CVE-2021-44228 (Log4Shell, chosen for its genuine
  public EPSS/KEV data) was run against the real DVWA lab through the
  actual Job Engine; `POST /api/intelligence/sync` triggered real HTTP
  calls to `cisa.gov`/`api.first.org` (observed in `cyberlab-worker`
  logs); resulting Finding scored `72/HIGH` with Asset criticality `LOW`,
  then `100/CRITICAL` after `PATCH`-ing the asset to `CRITICAL` —
  confirmed via API and the live browser UI (Top Risks, Finding detail,
  Asset Risk Overview). 292 tests green (211 pre-existing + 81 new).
- **`docs/api.md` fully rewritten**, not just appended to: corrected to
  reflect the real state of all mounted routers (Assets, legacy Targets,
  Continuous Recon, Risk/Intelligence), closing documentation debt left
  open since Phase 13/14 rather than compounding it.
- See [docs/phase-15-risk-score.md](docs/phase-15-risk-score.md) for the
  exact formula, ingestion strategy, and full verification log.

## Unreleased — Phase 14 — Continuous Recon + Diff Engine

- **`ScheduledJob`** (`backend/app/models/scheduled_job.py`): periodic
  re-execution of a tool+profile+params against an Asset. Fixed interval
  (`interval_seconds`, `MIN_INTERVAL_SECONDS = 300` floor) rather than cron
  expressions — deliberate simplicity, covers the "every 6 hours" use case
  without a cron parser dependency. `status` `ACTIVE`/`PAUSED`/`DISABLED`;
  `consecutive_failures`/`last_error` track *scheduling* failures (asset
  gone/unauthorized, tool/profile invalid) distinct from a scan that ran but
  failed; auto-pauses after 5 consecutive scheduling failures rather than
  retrying forever.
- **Ticker runs as a background thread inside `cyberlab-worker`**
  (`app/scheduling/ticker.py`, started from `app/jobs/worker.py`) — no new
  Docker service, no RQ Scheduler/APScheduler/Kafka/RabbitMQ/Redis lock
  dependency. Due schedules are claimed via Postgres `SELECT ... FOR UPDATE
  SKIP LOCKED` with `next_run_at` advanced and committed *before* any work
  happens — the Postgres-native reservation the spec asked for instead of a
  Redis lock. Verified with two real concurrent Postgres sessions that the
  same due row is never claimed twice.
- **A ScheduledJob triggers the exact same path as a manual job, always**:
  `app/jobs/service.py::prepare_job()` (Tool Registry validation, extracted
  from `POST /api/jobs`) and `app.targets.authorization.is_executable()`
  (unchanged since Phase 11) are called identically by the manual route, by
  schedule creation, by `POST /api/schedules/{id}/run`, and by every
  automatic tick — no parallel authorization logic exists anywhere in this
  phase. Verified: an asset whose authorization is revoked after a schedule
  is created has its next automatic run refused, not silently allowed.
- **Diff Engine** (`app/diff/engine.py` + `app/diff/service.py`): compares
  two normalized results (the same dicts already produced by
  `app/tools/parsers/`, no new result format) for the most recent *SUCCESS*
  Job with the same asset+tool+profile+params — no baseline, no comparison,
  this Job just becomes the new baseline. Detects, for the 4 tools whose
  parsers actually support it: nmap (port opened/closed, service/product/
  version changed), whatweb (technology added/removed/changed, HTTP status
  changed), sslscan (certificate subject/expiry changed — issuer and
  fingerprint are **not** detected, `app/tools/parsers/sslscan.py` doesn't
  extract them, documented rather than faked), gobuster (endpoint
  discovered/disappeared). Only scans the 20 most recent comparable jobs,
  never the full history.
- **`AssetChangeEvent`** (`backend/app/models/asset_change_event.py`): 9
  change types exactly as specified (`PORT_OPENED`/`PORT_CLOSED`/
  `SERVICE_CHANGED`/`TECHNOLOGY_ADDED`/`TECHNOLOGY_REMOVED`/
  `TECHNOLOGY_CHANGED`/`CERTIFICATE_CHANGED`/`HTTP_CHANGED`/`OTHER`),
  severity reuses the existing `Finding.Severity` enum. `old_value`/
  `new_value` are always coerced through `str()` before storage — they can
  originate from scanned-target data (service banners, whatweb plugin
  strings, certificate subjects) and are never trusted as anything but
  plain text; rendered frontend-side via escaped Vue interpolation, no
  `v-html` anywhere near them.
- **New API**: `GET/POST /api/assets/{id}/schedules`, `GET/PATCH/DELETE
  /api/schedules/{id}`, `POST /api/schedules/{id}/run`, `GET
  /api/assets/{id}/changes` (filters: `change_type`, `severity`, `before`).
  `ScheduledJobUpdateRequest` excludes `next_run_at`/`last_run_at`/
  `last_job_id`/`consecutive_failures`/`asset_id`/`project_id` — those are
  never directly settable via the API. `AssetChangeEvent` has no
  create/update route at all, only ever generated server-side.
- **Deleting an Asset (or a Target — same table since Phase 13) disables its
  schedules in the same transaction**, not eventually via the FK's `ON
  DELETE SET NULL` safety net — `app/scheduling/service.py::
  disable_schedules_for_asset()`, wired into both `DELETE /api/assets/{id}`
  and `DELETE /api/targets/{id}`.
- **Frontend**: `/targets/[id]` (the Asset detail page) gained two sections,
  wired exclusively to `/api/assets/...` (new Phase 14 code never touches
  the legacy `/api/targets` path, per this phase's Target/Asset convergence
  audit): **Continuous Recon** (schedule table with tool/profile/frequency/
  status/next-run/last-run, create form with dynamic profile picker,
  pause/resume/run-now/delete actions) and **Change Timeline** (severity
  icons, human-readable summaries, change-type/severity filters, link to
  the source scan). Loading/error/empty states throughout.
- **Verified end-to-end against the real Docker stack**: baseline nmap scan
  against `cyberlab-kali`, a real `nc -l -p 8888` listener started via
  `docker exec` to genuinely open a port, second scan → `PORT_OPENED`
  detected and persisted; listener killed, third scan → `PORT_CLOSED`
  detected. A real `ScheduledJob` (5-minute interval) fired automatically
  within one poll cycle, observed in `cyberlab-worker` logs. `docker
  compose restart cyberlab-worker` while the schedule was active: ticker
  restarted cleanly (log line reappears), a forced-due schedule after
  restart fired correctly with no duplicate and no loss. Full browser UI
  flow exercised live: create/pause/resume/run-now/delete a schedule,
  timeline rendering both real detected changes. 207 tests green (155
  pre-existing + 52 new), zero modified pre-existing test assertions.
- **Target/Asset convergence audit**: confirmed `Target` is still a plain
  alias to `Asset` (same table, Phase 13) — the three remaining
  `/api/targets` frontend call sites (`ai/index.vue`, `tools/index.vue`,
  `projects/[id].vue`) are read-only pickers/summaries that cannot diverge
  from `/api/assets` since they're the same rows; left as documented
  technical debt rather than touched, since none of this phase's new
  functionality depends on them.
- See [docs/phase-14-continuous-recon.md](docs/phase-14-continuous-recon.md)
  for the full design rationale and verification log.

## Unreleased — Phase 13 — Asset Model

- **`Target` generalized into `Asset`** (`backend/app/models/asset.py`): same
  table (renamed `targets` → `assets`), same primary keys, same rows —
  `Target`/`TargetType` (`backend/app/models/target.py`) become plain Python
  aliases (`Target = Asset`) rather than a duplicated parallel table, so
  every Phase 11 import, route, and test kept working unmodified. New
  fields: `type` (superset enum — adds `SUBDOMAIN`/`SERVICE`/`LAB_RESOURCE`
  to the existing `HOST`/`IP`/`DOMAIN`/`URL`/`CONTAINER`/`LAB`/`OTHER`),
  `criticality` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`, manual, defaults
  `MEDIUM`), `tags`, `technologies` (auto-populated from whatweb plugin
  detections, never directly editable), `first_seen`/`last_seen` (derived
  from real Job activity via the new `app/assets/activity.py`, `NULL` until
  an asset is actually scanned — never backfilled from `created_at`).
- **Migration** (`392e4638a4d8`): `ALTER TABLE targets RENAME TO assets`
  (Postgres updates the `jobs.target_id` FK automatically), column/enum
  renames (`target_type`→`type`, `target_metadata`→`asset_metadata`,
  `target_type` enum → `asset_type` with new values added via an autocommit
  block), new nullable/defaulted columns, and a backfill of
  `first_seen`/`last_seen` from existing `jobs` history. Backup taken
  (`pg_dump`) before applying against the real dev database; verified via
  `psql` (`\d assets`, FK target, `enum_range`).
- **New `/api/assets`** (`backend/app/api/routes/assets.py`) + `POST
  /api/projects/{id}/assets`: list (filters `project_id`/`type`/
  `criticality`/`authorization_status`/`search`), get, patch, delete,
  `/jobs`. `AssetUpdateRequest` deliberately excludes
  `first_seen`/`last_seen`/`technologies` — those are derived-only, a
  `PATCH` attempting to set them is silently ignored (absent from the
  schema), not a 422. `/api/targets` and `/api/projects/{id}/targets`
  untouched — same rows, verified visible from both endpoints
  interchangeably.
- **`app/assets/activity.py`**: `record_asset_activity()` called from
  `execute_job()` once a job linked to a `target_id` reaches a terminal
  state (SUCCESS or FAILED — the scan genuinely ran either way), updating
  `first_seen` (never regressed)/`last_seen` and merging in whatweb-detected
  technologies.
- **Frontend**: `/targets` and `/targets/[id]` migrated to `/api/assets`
  (same underlying rows, richer response) — expanded type/criticality/auth
  filters, criticality + tags on the create form, a detail-page criticality
  selector, tag add/remove, and a read-only Technologies/Activity panel.
  `/projects/{id}` (Targets tab) and the target pickers in `/ai`/`/tools`
  deliberately left on `/api/targets` for this phase — same data, no new
  fields shown there yet.
- **Security**: `/api/assets*` added explicitly to
  `test_every_api_route_is_guarded_when_auth_enabled` (verified, not just
  assumed from the path-prefix guard). No new imports under `app/ai/` — the
  static `test_ai_module_has_no_write_access_to_target_model` check passes
  unmodified. Full audit in
  [security.md](docs/security.md#phase-13--asset-model--audit-de-sécurité).
- **Verified end-to-end against the real Docker stack**, not just unit
  tests: created a project + `CONTAINER` asset via the authenticated API,
  ran a real `nmap` job against `cyberlab-kali` (`first_seen`/`last_seen`
  populated with the real job timestamp), started the real DVWA lab,
  created a `LAB_RESOURCE` asset (new enum value) against it with
  auto-inferred `LAB` authorization, ran `whatweb` twice
  (`technologies` populated with `Apache`/`DVWA`/`PHP`/...,
  `last_seen` advanced on the second run without regressing `first_seen`),
  and drove the actual browser UI (criticality change, tag add) with
  reload-confirmed persistence. 152 tests green (131 pre-existing +
  21 new), zero modified pre-existing test assertions.
- See [docs/phase-13-asset-model.md](docs/phase-13-asset-model.md) for the
  full design rationale and verification log.

## Unreleased — Phase 12 — Tool Registry expansion (31 tools)

- **Tool Registry grew from 3 tools to 31**, curated category by category
  (reconnaissance, DNS/network, web recon, web security, SSL/TLS,
  enumeration, vulnerability, OSINT, utilities) — not a Kali package dump.
  Every tool was verified actually installed (`which` inside the real
  container, not assumed) before being registered; apt package names were
  independently verified against a fresh `kalilinux/kali-rolling` pull
  (`bind9-dnsutils` for dig/host/nslookup, not the no-longer-existing
  `dnsutils`). `hydra`/`john`/`hashcat` were evaluated and deliberately
  **not** installed — neither fits the target_id-centric Job Engine model
  (offline hash files, or genuine brute-force amplification risk); `lynis`
  and `jq` are installed but intentionally **not registered** — both lack
  any real "network target" concept (lynis audits its own host, jq reads
  stdin) — all documented in [docs/tools.md](docs/tools.md) rather than
  silently omitted.
- **Tool Registry schema gained `profiles` and `ai_allowed`**
  (`backend/app/tools/schema.py`): a profile is a named, curated preset of
  argument values (e.g. nmap's `quick_scan`, `vulnerability_nse`) that
  `registry.build_command()` merges as defaults under the exact same
  per-argument validation as manually-typed options — a profile can never
  smuggle in a value the validator would otherwise reject. `ai_allowed`
  gates whether the AI Mission Planner may ever propose a tool at all. New
  `MANUAL_ONLY` risk tier (`sqlmap`) whose schema-level validator forces
  `ai_allowed: false` — impossible to define a `MANUAL_ONLY` tool the AI can
  reach, enforced at registry load time, not just convention.
- **`ai_allowed` enforced at two independent layers**
  (`backend/app/ai/planner.py`): non-`ai_allowed` tools are filtered out of
  the tool list *before* the prompt is even built (the model is never told
  they exist), and any proposed step is re-validated against the same
  allowlist afterward — proven with an adversarial test where a fake
  provider proposes `sqlmap` by name (a real registered tool, not a
  hallucination like `bash`) and the step is still stripped.
  `sqlmap.yaml` itself only exposes detection + database-name enumeration;
  `--dump`/`--os-shell`/`--sql-shell` are never declared as arguments, so
  they're structurally unreachable through this API regardless of caller.
- **`CAP_NET_RAW`** added to `cyberlab-kali` (`docker-compose.yml`) — a
  narrow addition on top of `cap_drop: ALL`, not a reversal of it — because
  `masscan` (raw SYN) and `traceroute` have no unprivileged mode, unlike
  nmap's existing `-sT`.
- **Tool Health** (`GET /api/tools/health`): non-destructive per-tool
  `--version`/`--help` probe (never a real scan), run in parallel across all
  31 tools (`kali/agent/main.py::_check_tool_health` +
  `asyncio.gather`/`run_in_executor`, ~5s total) — surfaced on the new
  `/tools` page as ✓ ready / ✕ broken / ⚠ not installed.
- **Frontend `/tools` fully rebuilt**: search, category/risk/AI filters,
  Tool Arsenal stat tiles, per-tool card with profile picker + target
  picker (existing Target dropdown or free text) replacing the old flat
  3-tool accordion. Dashboard gained a Tool Arsenal widget (installed/
  AI-enabled/manual-only counts + per-category breakdown).
- **AI Mission Planner now proposes tool+profile pairs**, not just raw
  options (`MissionStep.profile`, revalidated against the tool's actual
  profiles the same way `tool` itself is).
- 9 parsers total (masscan, gobuster, nuclei, sslscan, searchsploit added to
  the existing nmap/whatweb/nikto), each with a matching finding extractor;
  nuclei is the only extractor that trusts the tool's own severity rating
  rather than recomputing a conservative one, since nuclei templates already
  carry a community-reviewed rating, not a CyberLab heuristic guess. The
  other 22 tools expose raw output (`parser: none`), explicitly marked as
  such rather than faking normalization.
- **Four real bugs found via end-to-end testing against a real external
  target** (`scanme.nmap.org` — prior phases mostly tested against the local
  DVWA lab, which never exercised these paths):
  - `whatweb` could exit 1 (job marked `FAILED`, findings never extracted)
    despite a fully successful scan — a Ruby logger race between its
    default console logger and `--log-json=-` when both write to stdout.
    Fixed with `-q`.
  - `gobuster`/`ffuf` referenced a wordlist path that doesn't exist
    (`/usr/share/wordlists/dirb/` — the real path is `/usr/share/dirb/
    wordlists/`, reversed). Fixed in both YAML definitions.
  - `nikto` could stall until its job timeout without ever scanning: it
    phones home for a plugin-update check on every run by default, which
    can be rejected (403 observed); found no route to actually start the
    scan. Fixed with `-nocheck`; `basic_web_scan`'s timeout also raised from
    120s to 280s — nikto's full check set genuinely takes longer against a
    real Internet target than a local lab container, not a bug to hide.
  - **Kali agent crash on timeout** (`TypeError: can't concat str to
    bytes`): `subprocess.TimeoutExpired.stdout`/`.stderr` can come back as
    `bytes` even with `text=True`, and the handler did `bytes + str`,
    returning an opaque `500` instead of a clean timeout report. Fixed with
    defensive `bytes`→`str` coercion; regression test added
    (`kali/agent/tests/test_exec_timeout.py`).
  - A fifth, more serious bug surfaced while retesting the nikto fix: **RQ's
    own `job_timeout` defaults to 180s independently of the tool's own
    timeout budget**, silently killing the RQ job before a longer tool
    timeout (nikto's new 280s) ever got a chance to fire — and since
    `execute_job()` only caught three specific exception types, RQ's
    `JobTimeoutException` propagated uncaught, leaving the job's DB row
    stuck at `RUNNING` forever with no failure ever recorded. Fixed by
    passing `job_timeout=effective_timeout + 30` to `queue.enqueue()`
    (`backend/app/api/routes/jobs.py`), and — as defense in depth —
    `execute_job()` now has a catch-all handler that resolves *any*
    unexpected exception to `FAILED` with a message before re-raising, so a
    stuck-forever job can't happen again even from a cause nobody's hit yet.
  - A sixth, cosmetic-but-real bug: verifying the RQ fix through the actual
    AI Mission Planner "Run" button (not just curl) surfaced that
    `JobResponse` never declared a `profile` field at all -- a job created
    with a profile was correctly persisted (`jobs.profile` in Postgres had
    the right value) but the API silently omitted it from every response,
    so neither the frontend nor `curl` could ever see which profile a job
    actually used. Fixed by adding `profile: str | None` to `JobResponse`
    (`backend/app/schemas/job.py`); the scan detail page now shows it in
    the title (`nmap (quick_scan) → target`).
  All six followed REPRODUCE → DOCUMENT → FIX → TEST → RETEST; regression
  tests added for each rather than just patched and moved on.
- New tests: `backend/tests/tools/test_registry.py` (+13, profiles/
  ai_allowed/MANUAL_ONLY/multi-positional-args), `backend/tests/ai/
  test_ai_security_boundary.py` (+3, adversarial `ai_allowed` bypass
  attempts), `backend/tests/api/test_tools_health.py` (new, 3 tests),
  `backend/tests/jobs/test_tasks.py` (new — the `execute_job` catch-all
  regression test), `backend/tests/api/test_jobs.py` (+1, `job_timeout`
  wiring), `kali/agent/tests/test_exec_timeout.py` (new) — full suite (131
  tests) green.

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
