# Phase 21 — Tool Orchestrator (chaînage de jobs)

Livraison réelle de la Phase 21 planifiée dans [roadmap.md](roadmap.md#phase-21--tool-orchestrator-chaînage-de-jobs). Chaînage **déterministe** de jobs, entièrement séparé de la Phase 18 (Agents IA) — rappel explicite déjà donné pendant la conception de la Phase 18 : *"Ne pas confondre le futur orchestrateur IA de Phase 18 avec le Tool Orchestrator de Phase 21."*

## `MissionTemplate` — un nom, deux systèmes distincts

La roadmap nomme l'entité de définition `MissionTemplate` — un humain écrit une fois une liste ordonnée de `(tool, profile, condition)`, réutilisable contre n'importe quel Asset ensuite. **Aucune IA n'intervient nulle part dans ce module** : pas de provider, pas d'appel réseau, pas de planification. Conséquence directe : contrairement à la `Mission` de la Phase 18 (plan proposé par un LLM, nécessitant une revue humaine avant exécution), démarrer un `ChainRun` est déjà l'action délibérée de l'humain — **il n'y a pas d'étape DRAFT/APPROVED séparée**. Modèles, module (`app/chains/`, pas `app/ai/`), badges frontend : tout est distinct de la Phase 18, aucune réutilisation de `Mission`/`MissionStep`.

## Architecture

```text
app/models/mission_template.py — MissionTemplate, MissionTemplateStep (définition)
                                   ChainRun, ChainRunStep (une exécution réelle)
app/chains/conditions.py        — évaluation des 3 conditions (lecture pure, aucune écriture)
app/chains/service.py           — create_chain_run() / advance_chain_run() / cancel_chain_run()
app/api/routes/chains.py        — /api/chains/templates, /api/chains/runs
```

`advance_chain_run()` est le **4ᵉ appelant indépendant** de `is_executable()` + `prepare_job()` dans ce projet — après `POST /api/jobs` (async), `app/scheduling/ticker.py` (sync, Phase 14) et `app/ai/orchestrator.py` (sync, Phase 18). Jamais un chemin d'exécution parallèle : chaque `Job` créé par une chaîne passe par les deux mêmes fonctions pures que tout autre appelant.

### Isolation : hook, pas transaction partagée

Contrairement au hash SHA-256 de la Phase 20 (calcul local, inline dans la même transaction), l'avancement d'une chaîne **crée un nouveau `Job`** — exactement la même catégorie de risque que l'avancement de Mission (Phase 18). Le hook `advance_chain_run_for_job()` est donc isolé dans le `finally` le plus externe d'`execute_job()`, dans sa propre session, avec son propre `try`/`except` — un bug dans l'évaluation de condition ou la création du prochain `Job` ne peut jamais faire régresser le `Job` qui vient de se terminer avec succès.

### Séquence de sécurité d'`advance_chain_run()`

Verrouillage bloquant `SELECT ... FOR UPDATE` (pas `SKIP LOCKED`, même raisonnement que la Phase 18) → réconciliation d'une étape `QUEUED` contre le vrai statut de son `Job` → arrêt si une étape a réellement échoué → détermination de l'étape suivante → **évaluation de sa condition contre le `result` de l'étape précédente** → re-vérification `is_executable()` **à chaque étape**, jamais seulement à la création → `prepare_job()` → création + enfilement du `Job`.

### Divergence documentée : `SKIPPED` par condition ≠ `SKIPPED` par autorisation

Une condition légitimement non satisfaite (ex. "port 80 fermé") est un arrêt **normal et attendu** d'un pipeline conditionnel — l'étape passe `SKIPPED` mais le run passe **`COMPLETED`**, pas `FAILED`. C'est délibérément différent de la Phase 18, où `SKIPPED` signifie toujours une autorisation révoquée ou une erreur d'outil — toujours préoccupant, toujours `FAILED`. Ici, une autorisation révoquée ou un outil invalide restent `FAILED`, exactement comme en Phase 18 — seule la sémantique "condition de branchement non remplie" est nouvelle et volontairement distincte.

## Les 3 conditions (`app/chains/conditions.py`)

Volontairement limitées à trois, aucun DSL de branchement :

- **`PORT_OPEN`** — vérifie le `result` (forme nmap) : `{"ports": [80, 443]}`.
- **`TECHNOLOGY_DETECTED`** — réutilise `technologies_from_whatweb()` (Phase 13/14) tel quel, aucune réimplémentation.
- **`MIN_SEVERITY`** — vérifie le `result` (forme nuclei, sévérités en minuscules — table de rang dédiée, volontairement séparée de `_SEVERITY_FALLBACK` du Risk Score qui sert un tout autre usage sur l'enum majuscule).

### Cas spécial étroit : tags nuclei automatiques

Le seul détail de templating que la roadmap nomme explicitement ("nuclei, filtré sur les tags pertinents") : quand l'étape suivante est `nuclei`, que sa condition d'entrée est `TECHNOLOGY_DETECTED`, et qu'elle ne spécifie pas déjà `tags`, les technologies détectées par whatweb sont assainies (minuscules, caractères autorisés par le pattern réel `^[a-z0-9,\-]{1,128}$` de `nuclei.yaml`) et injectées dans `options.tags`. Ce n'est **pas** un mécanisme de templating général — juste ce cas précis, documenté comme tel.

## API

| Route | Description |
|---|---|
| `POST/GET/DELETE /api/chains/templates` | CRUD des templates. Validation à la création : outil/profil réellement enregistrés, première étape obligatoirement `ALWAYS`. |
| `POST /api/chains/runs` | Démarre un run **immédiatement** (pas d'approbation séparée). |
| `GET /api/chains/runs`, `GET /api/chains/runs/{id}` | Liste/détail. |
| `POST /api/chains/runs/{id}/cancel` | Kill switch — ne touche jamais un `Job` en cours (reste `POST /api/jobs/{id}/cancel`). |

Supprimer un template ne détruit jamais l'historique de ses runs : chaque `ChainRunStep` **copie** son `tool`/`profile`/`options`/`condition` à la création (même précédent que `MissionStep`, Phase 18) — `ChainRun.template_id` passe simplement à `NULL` (`ON DELETE SET NULL`).

## Frontend

Nouvelle page `/chains` (gestion des templates, formulaire d'étapes avec sélection outil/profil/condition) et nouvelle section "Tool Orchestrator" sur la page Asset (`AssetChainRun.vue`) — sélection d'un template, démarrage immédiat, polling borné (même idiome que `/ai/missions`), badges dédiés (`ChainRunStatusBadge`/`ChainRunStepStatusBadge`) délibérément non partagés avec ceux de la Phase 18.

## Vérification réelle (Docker + navigateur)

Migration `c3e7a9f2d5b8` appliquée sur la vraie base de dev (backup pris avant, cycle upgrade → downgrade → upgrade vérifié). Conteneurs reconstruits et redémarrés.

Template réel créé via l'UI (`nmap quick_scan` → `whatweb`, condition `PORT_OPEN` sur `[80, 443]`), lancé contre l'Asset DVWA réel :
1. Run démarré **immédiatement** à la création (`RUNNING`, étape 1 `QUEUED`) — aucune étape d'approbation.
2. `nmap` exécuté réellement par le worker RQ/l'agent Kali réel contre `cyberlab-lab-dvwa-c55eb6d4` → `SUCCESS`.
3. Le hook post-complétion a évalué la condition `PORT_OPEN` contre le **vrai** résultat nmap parsé (ports 80/443 non trouvés ouverts dans ce scan réel) → étape 2 correctement `SKIPPED` (`condition not met: PORT_OPEN`) → run correctement `COMPLETED` (pas `FAILED`) — la sémantique "arrêt normal, pas un échec" fonctionne en conditions réelles, pas seulement en test.
4. Le hook Mémoire IA (Phase 19) a échoué en parallèle (Ollama injoignable depuis ce conteneur à cet instant) — **totalement isolé**, sans aucun effet sur le `Job` (resté `SUCCESS`) ni sur le run de la chaîne (`COMPLETED`), preuve supplémentaire en conditions réelles que les hooks isolés d'`execute_job()` n'interfèrent jamais entre eux.
5. Le chemin "condition remplie → progression réelle" est couvert par `tests/jobs/test_chain_integration.py`, qui rejoue `execute_job()` avec un XML nmap réel montrant le port 80 ouvert et vérifie que l'étape suivante est correctement mise en file.

## Tests

67 nouveaux tests backend (559 au total) : évaluation des 3 conditions (18 cas), cycle de vie du service (création/progression/condition non remplie/échec d'autorisation/échec d'outil/annulation, 18 cas), **concurrence réelle à deux threads/deux sessions** prouvant qu'un seul `Job` est jamais créé pour une même étape, intégration `execute_job()` (avancement automatique réel, isolation, indépendance des 3 hooks), routes API (CRUD templates, cycle de vie des runs, sécurité — cible non autorisée), 5 nouvelles routes ajoutées à `test_every_api_route_is_guarded_when_auth_enabled`. 28 nouveaux tests frontend (123 au total).

## Ce qui n'est délibérément pas fait

- Pas de DSL de branchement complet, pas de conditions composées (ET/OU), pas de boucles.
- Pas de génération IA de templates — entièrement hors de cette phase.
- Aucune fusion avec `Mission`/`MissionStep`/l'orchestrateur IA (Phase 18) — modèles, module, badges, tout reste distinct.
- Aucun nouveau chemin d'exécution : chaque `Job` créé par une chaîne passe par `is_executable()` + `prepare_job()`, identique à tout autre `Job`.
