# Phase 19 — Mémoire IA par Projet/Asset

Livraison réelle de la Phase 19 planifiée dans [roadmap.md](roadmap.md#phase-19--mémoire-ia-par-projetasset). Deux livrables, tous deux strictement lecture + présentation, cohérents avec le principe déjà établi en Phase 18 (aucun agent IA n'exécute d'action, aucun agent IA n'a de capacité d'écriture au-delà de ce qui est explicitement documenté) :

1. **Résumé de projet stocké**, régénéré après l'activité de scan, jamais recalculé à chaque consultation.
2. **Questions temporelles** ("qu'est-ce qui a changé depuis le dernier audit ?") répondues via les données déjà structurées du Diff Engine (Phase 14) — la mémoire IA est une couche de présentation en langage naturel, pas un nouveau système de stockage.

## Décisions architecturales (divergences documentées)

La roadmap laissait plusieurs points ouverts ; décisions prises et raisons :

1. **Table dédiée `project_ai_summaries`, pas un `Finding` de type `SUMMARY`** — la roadmap proposait explicitement les deux options. `Finding` n'a aucune colonne discriminante (`type`/`kind`) ; en ajouter une uniquement pour y loger un résumé texte aurait conflaté un modèle entièrement structuré autour d'une vulnérabilité (severity/CVE/risk score/lifecycle) avec un contenu de nature complètement différente. Une table dédiée suit le précédent de chaque phase précédente (`Mission`, `GraphEdge`, `VulnerabilityIntel`).
2. **Pas de nouvelle infrastructure de "batch"** — la roadmap dit "après chaque batch de scans" mais CyberLab n'a aucune notion de batch. Un **cooldown temporel** (`_REGEN_COOLDOWN = 300s`, `app/ai/memory.py`) approxime ce comportement sans construire un système de suivi de batch : plusieurs jobs qui se terminent rapprochés (plusieurs étapes d'une Mission, ou un tick de scheduler touchant plusieurs assets) ne régénèrent le résumé qu'une fois. La régénération manuelle (`POST /api/ai/projects/{id}/summary/regenerate`) contourne le cooldown explicitement — intention humaine prioritaire sur l'heuristique.
3. **Hook isolé, pas le même patron que Diff Engine/Correlation/Graph** — ces trois-là (Phase 14/16/17) s'exécutent dans la même transaction que `execute_job()`, rapides et purement DB. Un appel IA est lent (10-30s observé en Phase 18) et réseau ; l'embarquer dans cette même transaction bloquerait chaque commit de Job réussi sur un appel Ollama. La régénération suit donc exactement le patron d'isolation déjà établi par `advance_mission_for_job` (Phase 18) : hook dans le `finally` le plus externe d'`execute_job()`, session entièrement séparée, `try`/`except` qui journalise et avale toute erreur sans jamais pouvoir toucher `job.status`.
4. **Aucun historique de conversation persisté** — `docs/ai.md` mentionne `AIConversation`/`AIMessage` comme limitation connue, mais ce n'est **pas dans la définition officielle de la Phase 19**. Le chat reste single-turn ; seul le system prompt est enrichi du résumé stocké + des derniers `AssetChangeEvent`, jamais un nouveau stockage de messages.
5. **Bug réel trouvé et corrigé pendant la vérification** : un simple `asyncio.run()` pour ponter l'appel IA async depuis le hook sync échoue silencieusement (absorbé par le `except Exception` d'`execute_job()`) si jamais appelé depuis un contexte ayant déjà une boucle asyncio active — ce qui n'arrive jamais en production réelle (le worker RQ n'a pas de boucle), mais arrivait silencieusement dans plusieurs tests préexistants (`tests/assets/test_activity.py`, entre autres) qui appellent `execute_job()` depuis une fonction de test elle-même `async def`. Corrigé par `_run_coro()` (`app/ai/memory.py`) : bascule vers un thread avec sa propre boucle si une boucle est déjà active, au lieu de silencieusement ne rien faire. Prouvé par un test dédié (`test_regenerate_works_even_when_called_from_a_running_event_loop`) et par la disparition des `RuntimeWarning: coroutine ... was never awaited` sur la suite complète.

## Architecture

```text
app/models/project_ai_summary.py — ProjectAISummary (nouveau, migration a1c4e6f9b3d2)
app/ai/agents/summary.py          — SummaryAgent (lecture seule, renvoie du texte libre)
app/ai/memory.py                  — regenerate_project_summary() / regenerate_project_summary_for_job()
                                     (sync, module-level -- mirroir du patron Phase 18)
app/api/routes/ai.py              — GET/POST /api/ai/projects/{id}/summary(/regenerate),
                                     ChatRequest.project_id (enrichissement du system prompt)
```

Pas de nouveau module `app/memory/` : `app/ai/` héberge déjà toute la génération IA (analyst, planner, orchestrator, agents Phase 18) — Phase 19 y ajoute sa propre paire agent-lecture-seule + service-avec-état, exactement le même découpage que `CorrelationAgent`+la route d'acceptation, ou `ReportAgent`+`POST /api/reports`.

### `SummaryAgent` — lecture seule, texte libre

Contrairement à `CorrelationSuggestion`/`ReportProposal` (Phase 18), un résumé ne porte aucun identifiant que le modèle pourrait halluciner — c'est du texte libre, pas une proposition structurée. Pas de revalidation d'ids nécessaire, seulement un plafonnement de longueur (2000 caractères).

### `regenerate_project_summary()` / `regenerate_project_summary_for_job()`

- Verrouille-relit-vérifie le cooldown avant tout appel IA (`existing.generated_at` comparé à `_now() - _REGEN_COOLDOWN`) — `force=True` (régénération manuelle) le contourne.
- Rassemble les données réelles du projet : Assets (`select(Asset).where(Asset.project_id == ...)`), répartition des Findings par sévérité (`GROUP BY Finding.severity`, jointure sur `Job.project_id`), 20 derniers `AssetChangeEvent` (jointure sur `Asset.project_id`, tri `detected_at DESC`).
- Upsert (jamais de doublon — `UniqueConstraint(project_id)`), commit, `based_on_job_id` renseigné uniquement quand la régénération vient du hook `execute_job()`.
- `regenerate_project_summary_for_job()` : no-op silencieux si le Job n'existe plus, n'est pas `SUCCESS`, ou n'a pas de `target_id` — même philosophie que `advance_mission_for_job` (Phase 18).

### Chat enrichi (`ChatRequest.project_id`)

Quand `project_id` est fourni : le Project est chargé (404 si inconnu), le `ProjectAISummary` stocké (s'il existe) et les 20 derniers `AssetChangeEvent` du projet sont injectés dans le system prompt via `CHAT_MEMORY_CONTEXT_TEMPLATE` (`app/ai/prompts.py`) — jamais recalculés, jamais une nouvelle requête IA de résumé à la volée. Le chat reste par ailleurs strictement inchangé (single-turn, pas d'historique persisté).

## API ajoutée

| Route | Description |
|---|---|
| `GET /api/ai/projects/{id}/summary` | Résumé stocké ; `404` si jamais généré. |
| `POST /api/ai/projects/{id}/summary/regenerate` | Régénération manuelle, contourne le cooldown. |
| `POST /api/ai/chat` (modifié) | `project_id` optionnel supplémentaire — enrichit le system prompt, ne crée jamais de résumé. |

## Frontend

Remplace le stub de l'onglet `ai` sur `pages/projects/[id].vue` (qui ne faisait que renvoyer vers `/ai`) par deux sections : la carte "Project Summary" (texte stocké, horodatage, bouton Regenerate, état vide explicite) et "Ask about this project" (question/réponse à un seul tour, grounded sur le résumé + les changements récents, pas d'historique de conversation). Chargement paresseux : le résumé n'est récupéré qu'à la première ouverture de l'onglet, cohérent avec "stocké, pas recalculé à chaque consultation".

## Vérification réelle (Docker + navigateur + Ollama réel)

Conteneurs `cyberlab-api`/`cyberlab-worker`/`cyberlab-frontend` reconstruits et redémarrés, migration `a1c4e6f9b3d2` appliquée (upgrade → downgrade → upgrade vérifié contre la vraie base de dev, backup réel pris avant).

Sur le projet réel "Phase 16 E2E" (21 findings informationnels réels, DVWA, changements réels de Phase 16) :
1. Onglet `ai` ouvert → `GET /summary` → `404` correctement affiché comme état vide ("No summary generated yet").
2. `Regenerate` cliqué → appel réel à Ollama (`qwen2.5-coder:3b`) → résumé généré **factuellement exact** : criticité medium de l'asset DVWA correctement citée, 21 findings informationnels correctement comptés, changements récents de suppression de technologie correctement décrits — aucune donnée inventée.
3. "Ask about this project" → "What changed most recently on this project?" → réponse **grounded** citant exactement le `AssetChangeEvent` réel le plus récent (`TECHNOLOGY_REMOVED`, champ, horodatage exact) — jamais inventée.
4. Logs API propres sur toute la séquence : `404` attendu sur le premier `GET`, `200` sur `regenerate` et `chat`, aucune erreur 500.

## Tests

28 nouveaux tests backend (492 au total) : `SummaryAgent` (troncature, réponse vide, non-JSON), `app/ai/memory.py` (création, cooldown respecté/contourné, upsert sans duplication, comptages de sévérité réels, résolution Job→Asset→Project pour le hook, no-op sur Job non-`SUCCESS`/sans `target_id`/inconnu, **robustesse `asyncio.run()` prouvée par un test appelé depuis une vraie boucle asyncio active**), intégration `execute_job()` (régénération automatique réelle, isolation Job/Mémoire, indépendance du hook Mission et du hook Mémoire), routes API (résumé/régénération/chat enrichi, 404 avant génération, chat n'écrit jamais de résumé), 2 nouvelles routes ajoutées à `test_every_api_route_is_guarded_when_auth_enabled`. 2 nouveaux tests frontend (95 au total). Garde-fous statiques Phase 18 (`rglob` récursif sur `app/ai/`) couvrent automatiquement `app/ai/memory.py` et `app/ai/agents/summary.py` sans modification.

## Ce qui n'est délibérément pas fait

- Pas d'historique de conversation persisté (`AIConversation`/`AIMessage`) — hors définition officielle de cette phase.
- Pas de nouvelle infrastructure de planification/batch — réutilise le hook `execute_job()` déjà existant, cooldown temporel simple.
- Aucune écriture par un agent : `SummaryAgent` n'a aucun accès `Session` (vérifié statiquement), seul `app/ai/memory.py` persiste, exactement comme le Correlation/Report Agent et leurs routes dédiées en Phase 18.
- Aucune modification de `app/diff/`, `app/scheduling/`, ou des hooks Phase 14/16/17/18 déjà en place — uniquement un cinquième hook ajouté, indépendant, dans le `finally` d'`execute_job()`.
