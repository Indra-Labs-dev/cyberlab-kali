# Phase 17 — Security Graph

## Objectif

Répondre à des questions comme *« Quels services expose cet Asset ? »*, *« Quel CVE est lié à ce Finding ? »*, *« Que trouve-t-on à 2 hops de cet Asset ? »* via une première couche de graphe de connaissances de sécurité — locale, fiable, explicable. Pas d'Attack Path, pas de moteur de règles générique, pas de nouvelle base de données : PostgreSQL uniquement.

## Audit initial

Avant tout code, vérification de ce qui existe réellement (pas supposé) :

- **`Asset.technologies`** (`app/models/asset.py`) existe déjà et est peuplé depuis whatweb (`app/assets/activity.py::record_asset_activity`, appelé depuis `execute_job`) — donnée réelle, jamais à re-dériver.
- **`Finding.evidence`** pour nmap/masscan porte `port`/`protocol`/`state`/`service` directement ; whatweb/nuclei n'ont pas de port fiable (application détectée ≠ port confirmé ouvert).
- **`Finding.cve_ids`** existe depuis la Phase 15 — jamais de table CVE locale à créer, uniquement `Finding.cve_ids` et `vulnerability_intel.cve` (déjà là).
- **`FindingRelation`** (Phase 16) est *déjà* littéralement un edge `Finding → Finding RELATED_TO` avec `rule`/`reason` — réutilisé tel quel, jamais recalculé.
- **`Job.target_id`** relie un Job (et donc ses Findings) à un `Asset` — c'est la même relation déjà utilisée par le Diff Engine et le Risk Score pour scoper leur traitement à un Asset.
- Pas de notion de "Service" persistante nulle part — un nœud virtuel, jamais une table.
- Pas de relation Asset↔Asset provable dans les données existantes, sauf une : deux Assets du même projet observés avec au moins une technologie en commun (`Asset.technologies`, déjà réel).

**Ce qui alimente le graphe sans rien inventer** : `Job.target_id` (HAS_FINDING), `Finding.evidence` nmap/masscan (EXPOSES), `Asset.technologies` (USES_TECHNOLOGY), `Finding.cve_ids` (REFERENCES_CVE), `FindingRelation` (RELATED_TO Finding↔Finding), technologies partagées au sein d'un même projet (RELATED_TO Asset↔Asset).

**Ce qui manque et n'est pas inventé** : pas de service pour whatweb/nuclei (pas de port fiable), pas de CVE local détaillé (juste l'identifiant), pas de relation Asset↔Asset hors partage de technologie prouvé, pas de relation entre projets différents.

## Modèle Graph — PostgreSQL uniquement

Une seule table, `graph_edges` (`backend/app/models/graph_edge.py`) :

```
id, from_type, from_id, to_type, to_id, relation, source, reason, edge_metadata, created_at, updated_at
UNIQUE(from_type, from_id, to_type, to_id, relation)
```

Pas de table `graph_nodes` séparée. `ASSET`/`FINDING` référencent de vraies lignes (`from_id`/`to_id` = UUID en chaîne) ; `CVE`/`SERVICE`/`TECHNOLOGY` sont des nœuds **virtuels** identifiés par une clé naturelle (`CVE-2021-44228`, `80/tcp`, `Apache`) — jamais de table CVE/Service/Technology locale créée juste pour satisfaire le modèle du graphe.

Aucune installation de Neo4j/ArangoDB/Elasticsearch/Kafka — à l'échelle actuelle de CyberLab (quelques centaines d'edges par Asset), une CTE récursive sur une table indexée suffit et reste transactionnellement cohérente avec le reste du système.

## Nodes

`ASSET`, `FINDING`, `CVE`, `SERVICE`, `TECHNOLOGY` — exactement les 5 types minimums demandés, aucun autre. Un nœud est hydraté (label/metadata réels) uniquement pour `ASSET`/`FINDING` en relisant leur vraie table ; les nœuds virtuels utilisent leur `external_id` comme label, il n'y a rien d'autre à afficher.

## Edges — 5 règles fixes, chacune avec provenance obligatoire

`backend/app/graph/builder.py::build_graph_for_asset()` — jamais un moteur de règles générique, 5 fonctions Python fixes :

| Edge | Condition réelle | Source | Exemple de `reason` |
|---|---|---|---|
| `ASSET -[HAS_FINDING]-> FINDING` | Finding rattaché à un Job dont `target_id` = cet Asset | `system` | *"Finding "..." was produced by a job that scanned this asset."* |
| `ASSET -[EXPOSES]-> SERVICE` | **uniquement** nmap/masscan, `evidence.state == "open"` | outil | *"nmap observed 80/tcp open on this asset, running http."* |
| `ASSET -[USES_TECHNOLOGY]-> TECHNOLOGY` | chaque entrée de `Asset.technologies` (déjà réel) | `whatweb` | *"whatweb identified "Apache" on this asset."* |
| `FINDING -[REFERENCES_CVE]-> CVE` | chaque entrée de `Finding.cve_ids` | outil | *"nuclei identified CVE-2021-44228 in finding "..."."* |
| `FINDING -[RELATED_TO]-> FINDING` | miroir de `FindingRelation` (Phase 16), jamais recalculé ici | `phase16_correlation` | reprend le `reason` de Phase 16 tel quel |
| `ASSET -[RELATED_TO]-> ASSET` | deux Assets **du même projet** partageant ≥1 technologie observée | `system` | *"Both assets have been observed running: Apache."* |

Whatweb/nuclei ne produisent **jamais** d'`EXPOSES` (pas de port confirmé) — vérifié explicitement (`test_build_graph_never_exposes_service_for_whatweb`). Deux Assets de projets différents ne sont **jamais** liés, même s'ils partagent une technologie — vérifié (`test_build_graph_never_links_assets_across_different_projects`), ce qui garantit par construction qu'un traversal ne peut jamais franchir une frontière de projet via cette règle.

## Graph Builder — idempotence

`_upsert_edge()` utilise `INSERT ... ON CONFLICT (from_type, from_id, to_type, to_id, relation) DO UPDATE` — atomique en une seule instruction, plus simple que l'upsert de Finding (Phase 16, `SELECT FOR UPDATE` + SAVEPOINT) car un edge ne porte aucun état accumulé à fusionner (pas d'`observation_count`, pas de règle "ne jamais écraser une valeur connue par NULL") : c'est la description d'un fait actuellement vrai, toujours sûr à écraser entièrement par le dernier calcul.

Rejoué deux fois sur les mêmes données → même nombre d'edges (`test_build_graph_is_idempotent`), vérifié réellement contre le stack Docker (42 edges avant/après un rebuild complet, avant/après un re-scan whatweb, avant/après `docker compose restart cyberlab-worker`).

`app/graph/builder.py::delete_edges_for_finding()` nettoie les edges d'un Finding supprimé (`graph_edges` n'a pas de contrainte FK vers `findings` — `SERVICE`/`CVE`/`TECHNOLOGY` n'ont pas de table à `CASCADE`) — vérifié (`test_delete_edges_for_finding_removes_related_edges`).

## Traversal — CTE récursive, cycle-safe, profondeur limitée

`backend/app/graph/queries.py::local_graph()` — `WITH RECURSIVE`, jamais une boucle Python multi-requêtes :

1. Un `graph_edges` réel est directionnel (`relation` a un sens : `EXPOSES` part toujours de l'Asset), mais explorer *"ce qu'il y a autour de ce nœud"* doit marcher dans les deux sens — une CTE `bidirectional_edges` duplique chaque edge dans les deux sens avant le traversal (la direction d'origine reste dans les edges renvoyés à l'appelant, seul le *walk* l'ignore).
2. Protection anti-cycle : un tableau `visited` accumule chaque nœud déjà rencontré sur le chemin courant ; l'étape récursive refuse d'avancer vers un nœud déjà dans `visited`. Vérifié avec un vrai cycle à 3 nœuds (`A → B → C → A`, un cas réel que la règle Asset↔Asset peut produire dès 3 assets partageant une technologie) : le traversal trouve les 3 edges puis s'arrête, sans jamais boucler (`test_local_graph_handles_a_real_3_node_cycle_without_looping`, ~46ms en conditions réelles).
3. `MAX_GRAPH_DEPTH = 3`, appliqué **côté serveur** indépendamment de ce qu'un appelant demande — `depth=4` est rejeté (`InvalidDepthError` → `422` côté API), jamais silencieusement clampé sans erreur.

## API

```
GET  /api/graph/assets/{id}?depth=1|2|3          404 si l'asset n'existe pas
GET  /api/graph/findings/{id}?depth=              404 si le finding n'existe pas
GET  /api/graph/nodes/{type}/{id}?depth=          400 si type inconnu ; 404 pour ASSET/FINDING inconnu ; jamais 404 pour un nœud virtuel (CVE/SERVICE/TECHNOLOGY) inconnu — graphe vide, réponse honnête
GET  /api/graph/projects/{id}?depth=              404 si le projet n'existe pas ; fusionne le graphe de chaque Asset du projet, borné à 50 assets
POST /api/graph/rebuild  {project_id?, asset_id?}  202, via la queue RQ existante (même substrat qu'un scan Job ou la sync Phase 15)
```

Toutes protégées par le même middleware d'authentification (`test_every_api_route_is_guarded_when_auth_enabled` étendu). `depth` validé par Pydantic (`ge=1, le=MAX_GRAPH_DEPTH`) **et** par `local_graph()` elle-même (défense en profondeur, utile aussi hors contexte API).

`POST /api/graph/rebuild` ne s'exécute jamais dans la requête HTTP — enfilé via RQ (`202` immédiat), ce qui sérialise gratuitement les rebuilds concurrents (un worker RQ par défaut traite un job à la fois) sans verrou applicatif supplémentaire.

## Frontend — `SecurityGraph.vue` (Cytoscape.js)

Aucune bibliothèque de graphe n'existait dans `package.json` (seul `@xterm/xterm` pour le terminal). **Cytoscape.js** choisi : conçu spécifiquement pour ce type de graphe typé nœuds/arêtes à quelques centaines d'éléments, zoom/pan/sélection intégrés, aucun couplage à un framework, pas de WebGL requis (contrairement à sigma.js) — chargé dynamiquement (`await import("cytoscape")`) dans `onMounted`, même pattern que `@xterm/xterm` sur la page Terminal (évite tout problème de SSR).

Fonctionnalités : zoom/pan (natif Cytoscape), recherche (filtre par sous-chaîne sur le label), filtres par type de nœud (boutons ASSET/FINDING/CVE/SERVICE/TECHNOLOGY), profondeur 1/2/3, Fit, Reset view. Nœuds colorés/formés par type (cercle bleu Asset, losange ambre Finding, triangle rouge CVE, rectangle vert Service, hexagone violet Technology) — cohérent avec la palette déjà utilisée sur les pages Findings.

Clic sur un nœud → panneau latéral : type, label, métadonnées réelles (hostname/criticality pour un Asset ; severity/status/risk_score pour un Finding), lien `Open Asset →`/`Open Finding →` vers la page CyberLab existante, et la liste de ses connexions (`relation` + `reason` humainement lisible pour chacune) — jamais un lien opaque.

## Asset View

Nouvelle section "Security Graph" sur `/targets/[id]`, après Risk Overview — n'a remplacé aucune section existante.

## Project View

Nouvel onglet "Graph" sur `/projects/[id]` (même système d'onglets que overview/targets/scans/findings/labs/ai/reports), affichant le graphe fusionné de tous les Assets du projet (borné à 50 assets, `_MAX_PROJECT_ASSETS`).

## Performance

Mesuré en conditions réelles contre l'Asset DVWA E2E (21 Findings, 1 Service, 10 Technologies, 10 relations Finding↔Finding) :

- `local_graph()` depth=1 : 32 edges, temps SQL négligeable (<50ms).
- depth=3 sur un vrai cycle synthétique à 3 nœuds : ~46ms, aucune explosion combinatoire.
- Le graphe Project est borné à 50 assets (`_MAX_PROJECT_ASSETS`) — pas de dump de plusieurs milliers de nœuds.

Aucune optimisation prématurée au-delà de ces bornes ; à réévaluer si un projet atteint des milliers d'Assets/Findings (hors échelle actuelle de CyberLab).

## Tests

**39 tests nouveaux** (10 builder, 7 traversal/queries, 15 API, plus les 3 déjà comptés dans les extensions d'auth) — voir `backend/tests/graph/`. Couvre : chaque type d'edge, idempotence, suppression de Finding, cycle réel à 3 nœuds, profondeur 1/2/3 valides et rejet de 0/-1/4, injection SQL via `node_id` (payload stocké comme texte inerte, table intacte), non-fuite entre projets, `POST /rebuild` (mock de la queue, même pattern que le test Phase 15 `test_intelligence_sync_trigger_enqueues`).

## Sécurité

Voir la section dédiée dans [security.md](security.md#phase-17--security-graph--audit-de-sécurité).

## E2E réel

Asset `DVWA E2E` (déjà créé en Phase 16) réutilisé, nmap/whatweb/nuclei déjà réels. **Bug potentiel évité par l'audit** : le graphe a d'abord été construit et vérifié directement en base (`build_graph_for_asset` appelé en script Python contre le vrai Postgres) avant toute intégration API/frontend — 42 edges corrects dès le premier essai (21 HAS_FINDING, 1 EXPOSES, 10 USES_TECHNOLOGY, 10 RELATED_TO). Vérifié ensuite via l'API réelle (`curl` contre `cyberlab-api`) puis dans un vrai navigateur : graphe rendu sur `/targets/{id}` et `/projects/{id}`, clic sur le nœud `SERVICE 80/tcp` et sur l'Asset lui-même ouvrant le panneau latéral avec les vraies connexions/raisons, sélecteur de profondeur 1/2/3 fonctionnel, aucune erreur console. `POST /api/graph/rebuild` vérifié traité par le vrai worker RQ dans les logs.

## Worker Restart

`docker compose restart cyberlab-worker` exécuté avec 42 edges déjà en base. Après redémarrage : rebuild complet déclenché (`POST /rebuild`) → toujours 42 edges ; nouveau scan whatweb réel exécuté → toujours 42 edges ; requête explicite de doublons (`GROUP BY from_type, from_id, to_type, to_id, relation HAVING count(*) > 1`) → 0 résultat. Aucune duplication, perte, ou corruption.

## Migration

`alembic/versions/496b351d1744_security_graph_edges.py` — additive uniquement (une nouvelle table, rien de modifié). Backup réel pris (`pg_dump -F c`) avant tout changement. `upgrade` → vérifié (`\d graph_edges`, contrainte unique + 2 index présents) → `downgrade` → vérifié (table absente) → `upgrade` à nouveau — les trois exécutés contre la vraie base de développement, réalisés **avant** toute donnée réelle insérée dans `graph_edges` (le graphe étant reconstructible à tout moment depuis les Findings/Assets existants, aucune relation historique n'est fabriquée pour compenser).

## Limites connues / hors scope

Explicitement **non traité** dans cette phase :

- **Attack Path Analysis / Exploit Chains / exploitation autonome** — Phase 18+, le graphe fournit seulement les fondations.
- **Neo4j / toute base graphe externe** — PostgreSQL uniquement, suffisant à l'échelle actuelle.
- **Moteur de règles générique / DSL de corrélation** — 5 fonctions Python fixes.
- **Multi-worker / multi-Kali / SIEM / Event Bus / Kafka / RBAC / multi-tenant / auto-remédiation / Plugin Marketplace** — hors scope, cohérent avec les limites déjà documentées en Phase 16.
- **`REFERENCES_CVE` non re-vérifié par un scan nuclei live contre DVWA dans cette phase précise** : le template de test Phase 15 (`CyberLab Phase 15 E2E Verification Template`, qui référençait CVE-2021-44228) avait été délibérément retiré du conteneur Kali après la vérification E2E de la Phase 15 (nettoyage documenté dans `phase-15-risk-score.md`) ; aucun template actuellement chargé dans `cyberlab-kali` ne produit de manière fiable un CVE contre une DVWA standard. La règle `REFERENCES_CVE` est donc vérifiée par un test unitaire réel contre PostgreSQL (`test_build_graph_creates_references_cve_from_finding_cve_ids`, données réelles en base, pas de mock), mais pas par un nouveau scan nuclei live dans cette phase — signalé honnêtement plutôt que simulé.
- **Pas de fabrication de relations historiques** : le graphe n'a jamais été rétro-peuplé pour des données antérieures à cette phase autrement qu'en le (re)construisant depuis les Findings/Assets réellement existants au moment du build — jamais une relation inventée pour "combler" une absence de données.
