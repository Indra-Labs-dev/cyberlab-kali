# Phase 24 — Attack Path Analysis (léger)

## Origine et écart assumé par rapport à la roadmap

La roadmap ([roadmap.md](roadmap.md), §8) gate explicitement cette piste derrière « le Security Graph (Phase 17) alimenté par de vraies données pendant plusieurs mois » — condition non remplie ici (CyberLab reste un déploiement de lab/dev). Cette phase a été lancée malgré tout, par décision explicite de l'utilisateur, pas parce que le prérequis était atteint. Conséquence assumée : les chemins trouvés reflètent le graphe actuel, volontairement petit — la fonctionnalité elle-même (le moteur de recherche de chemin) est correcte et testée indépendamment du volume de données ; seule sa valeur démontrée sur ce jeu de données reste limitée pour l'instant.

## Objectif

Rechercher des **chemins** (pas un voisinage — voir ci-dessous) dans `graph_edges` (Phase 17, inchangé) selon deux modes :

1. **Vers les actifs critiques** — `source → chemins possibles → tout Asset CRITICAL`.
2. **Explicite source → cible** — deux nœuds choisis à la main, utile pour valider le moteur avec les données limitées déjà présentes.

Contrainte non négociable : chaque chemin est une **hypothèse structurelle**, jamais une preuve d'exploitabilité. Aucun score d'exploitabilité/probabilité n'est calculé — décision délibérée, pas un oubli reporté à plus tard.

## Ce qui existait déjà (Phase 17, réutilisé tel quel)

- `graph_edges` (`app/models/graph_edge.py`) — table relationnelle unique, 5 types de relation, 5 types de nœud.
- `app/graph/queries.py::local_graph()` — traversal récursif *de voisinage* (« tout ce qui est à N sauts »), cycle-safe (tableau `visited`), profondeur bornée. **Ne fait pas** de recherche de chemin source→cible — c'est le vrai écart comblé par cette phase, pas une réimplémentation.
- `app/api/routes/graph.py` — 4 routes de voisinage + `/rebuild`, inchangées.

## Ce qui est nouveau

### `app/graph/queries.py`

- `_PATH_TRAVERSAL_SQL` — même technique `bidirectional_edges` + tableau `visited` que `local_graph()`, étendue pour porter le tableau ordonné des `id` d'arêtes empruntées (`path_edge_ids`), pas seulement l'ensemble des nœuds atteignables.
- `_enumerate_paths()` — tous les chemins bruts (cycle-safe, bornés à `MAX_ATTACK_PATH_HOPS`) depuis un nœud de départ.
- `_build_paths_response()` — mise en forme partagée : cap à `MAX_ATTACK_PATHS` (chemins les plus courts d'abord — un critère purement structurel, jamais un score), résolution des arêtes *dans l'ordre parcouru* (contrairement à `local_graph()` qui déduplique en un ensemble), reconstruction de la séquence de nœuds en marchant depuis la source (évite toute hypothèse sur la direction `from`/`to` stockée, puisque le parcours est bidirectionnel).
- `find_paths_to_critical_assets()` — filtre les chemins bruts sur « arrive à un Asset CRITICAL différent du nœud de départ » (un asset déjà CRITICAL n'est jamais son propre chemin de 0 saut).
- `find_paths_between()` — filtre sur « arrive exactement à la cible demandée » ; source == cible retourne une liste vide sans même interroger la base.

Constantes, toutes obligatoires par consigne explicite :

| Constante | Valeur | Rôle |
|---|---|---|
| `MAX_ATTACK_PATH_HOPS` | 4 | Un saut de plus que `MAX_GRAPH_DEPTH` (3) — ce dernier est calibré pour une vue de voisinage lisible à l'écran, pas pour atteindre un nœud précis potentiellement plus loin |
| `MAX_ATTACK_PATHS` | 20 | Chaque chemin doit être lu et vérifié manuellement par un humain — le plafond est choisi pour ça, jamais pour l'exhaustivité |
| `_MAX_RAW_PATH_ROWS` | 2000 | Filet de sécurité sur les lignes brutes remontées par la CTE avant filtrage — généreux compte tenu de l'échelle réelle du graphe (« centaines d'arêtes, jamais des millions », déjà documenté Phase 17), pas un réglage de production |

### `app/schemas/graph.py`

`AttackPath` (`hops`, `nodes`, `edges`), `AttackPathsResponse` (`disclaimer`, `seed`, `truncated`, `paths`) — `disclaimer` est présent sur **toute** réponse, y compris une liste vide.

### `app/api/routes/graph.py`

- `GET /api/graph/attack-paths/critical/{node_type}/{node_id}?max_hops=`
- `GET /api/graph/attack-paths/between/{from_type}/{from_id}/{to_type}/{to_id}?max_hops=`

Validation identique à `get_node_graph()` (factorisée dans `_ensure_node_exists()`, sans toucher la route existante) : 404 sur un Asset/Finding inconnu ou malformé, jamais de 404 sur un type virtuel (CVE/SERVICE/TECHNOLOGY, sans table de référence).

### Frontend

- `useGraph.ts` — `loadAttackPathsToCriticalAssets()`/`loadAttackPathsBetween()`.
- `AttackPaths.vue` (nouveau) — délibérément une liste de chemins, pas un rendu Cytoscape supplémentaire comme `SecurityGraph.vue` : une poignée de nœuds chaînés se lit plus clairement comme « voici une hypothèse précise à vérifier » qu'un graphe dense, et reste cohérent avec l'esprit « léger » de la roadmap. Bandeau d'avertissement toujours visible + texte `disclaimer` de l'API lui-même rendu séparément (jamais juste le bandeau statique — le texte de l'API reste la source de vérité si son libellé évolue).
- `pages/graph/index.vue` — bascule Neighborhood / Attack Paths ajoutée, `SecurityGraph.vue` inchangé.

## Vérification en conditions réelles

`curl` authentifié contre la base de dev réelle (pas de données fictives) :

- `GET .../between/ASSET/{DVWA}/TECHNOLOGY/Apache` → 1 chemin réel, 1 saut, arête `USES_TECHNOLOGY` dérivée par whatweb (Phase 17).
- `GET .../critical/ASSET/{DVWA}` avant tout changement → liste vide (honnête : aucun asset `CRITICAL` n'existait).
- `Asset.criticality` de DVWA basculé à `CRITICAL` via la route `PATCH /api/assets/{id}` déjà existante (une action réelle et réversible, pas une arête ou une donnée inventée) → `GET .../critical/TECHNOLOGY/Apache` trouve bien le chemin vers DVWA désormais critique → `criticality` restauré à `MEDIUM` immédiatement après, état de la base identique à avant le test.
- UI vérifiée visuellement (bascule Neighborhood/Attack Paths, bandeau d'avertissement, sélection de nœud, changement de mode). Le round-trip complet clic-jusqu'à-résultat n'a pas pu être vérifié dans le navigateur de cette session : `NUXT_PUBLIC_API_BASE` pointe vers l'IP LAN réelle de la machine (`10.27.185.35`, correcte pour l'usage réel de l'app), injoignable depuis le bac à sable de test — confirmé en reproduisant le même blocage sur la recherche Neighborhood existante et inchangée, donc sans rapport avec cette phase.

## Tests

- `tests/graph/test_attack_paths.py` (15) : chemin direct/multi-sauts, aucun chemin, source == cible, profondeur maximale respectée, rejet au-delà du plafond de sauts, type de nœud inconnu, cycle réel à 3 nœuds (parcours bidirectionnel confirmé — trouve à la fois le raccourci direct et le chemin long), plafond `MAX_ATTACK_PATHS` avec `truncated=True`, absence de tout champ score/probabilité, actif déjà critique jamais son propre chemin de longueur 0, actifs non-critiques ignorés.
- `tests/graph/test_attack_paths_api.py` (12) : 404/400 cohérents avec les routes existantes, type virtuel jamais 404, rejet HTTP du dépassement de plafond de sauts, injection SQL dans `node_id` inerte (table intacte ensuite), `disclaimer` toujours présent, bout-en-bout via de vraies arêtes dérivées par `app/graph/builder.py` (pas des arêtes synthétiques de test).
- `frontend/app/composables/useGraph.test.ts` (+4), `frontend/app/components/AttackPaths.test.ts` (8, nouveau) : URLs générées correctes (dont encodage des identifiants spéciaux), bandeau toujours visible, bascule de mode, désactivation du bouton Search tant que les nœuds requis ne sont pas choisis, absence de tout vocabulaire de score.

## Migration

Aucune. `graph_edges` et `Asset.criticality` (Phase 13/17) suffisaient tels quels — confirmé avant d'écrire le moindre code, tête Alembic unique (`e5f1a9c7d3b2`) inchangée.

## Ce qui n'est délibérément pas fait

- **Aucun score d'exploitabilité/probabilité** — contrainte explicite de cette phase, pas une limitation technique à lever plus tard sans re-décision explicite.
- **Aucune donnée inventée** pour rendre le graphe plus riche — la valeur démontrable de cette fonctionnalité reste bornée par le volume réel de données déjà collecté, assumé (voir section « écart »).
- **Pas de fusion avec `local_graph()`/`SecurityGraph.vue`** — un chemin et un voisinage répondent à des questions différentes ; les forcer dans un seul composant/une seule requête aurait compliqué les deux sans bénéfice réel.
