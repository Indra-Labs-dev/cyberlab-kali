# IA locale (Ollama)

CyberLab réutilise l'instance Ollama déjà active sur l'hôte (`host.docker.internal:11434`) — voir [architecture.md](architecture.md). Aucun modèle n'est téléchargé ni géré par CyberLab lui-même.

## Abstraction (`backend/app/ai/`)

```
provider.py     — interface abstraite AIProvider.generate(prompt, system, json_mode) -> str
ollama.py       — OllamaProvider : implémentation concrète (appelle /api/generate)
schemas.py      — AnalysisResult, MissionPlan, MissionStep, ChatMessage/Response,
                   CorrelationSuggestion, ReportProposal (Phase 18)
prompts.py      — templates système + construction des prompts
parsing.py      — extraction JSON tolérante (fences markdown, texte parasite)
analyst.py      — AIAnalyst : job de scan -> AnalysisResult
planner.py      — AIMissionPlanner : (target, goal) -> MissionPlan
orchestrator.py — MissionOrchestrator (Phase 18) : cycle de vie des Missions
memory.py       — regenerate_project_summary() (Phase 19) : mémoire IA par projet
agents/
  correlation.py — CorrelationAgent (Phase 18, lecture seule)
  report.py       — ReportAgent (Phase 18, lecture seule)
  summary.py      — SummaryAgent (Phase 19, lecture seule)
```

Changer de provider (un autre modèle Ollama, ou plus tard un autre backend) ne touche que `ollama.py` — `analyst.py`/`planner.py` ne dépendent que de l'interface `AIProvider`.

## AI Analyst

`POST /api/ai/analyze/{job_id}` : prend un job terminé (`SUCCESS`/`FAILED`), envoie l'outil/la cible/le résultat parsé/le stdout au modèle avec un prompt qui force une sortie JSON structurée (`{"risk", "summary", "findings", "recommendations", "next_steps"}`, contrainte via l'option Ollama `format: "json"`). Le résultat est persisté sur `Job.ai_analysis` (rejouable, visible dans l'UI sans ré-appeler le modèle). Si la sortie n'est pas un JSON exploitable, `AnalysisResult` retombe proprement sur `risk: "INFO"` avec la réponse brute conservée (`raw_response`) plutôt que de planter.

## AI Mission Planner

`POST /api/ai/plan` : prend `{target, goal}`, transmet au modèle la liste réelle des outils du Tool Registry (nom, description, arguments) et lui demande un plan JSON (`{"steps": [...]}`) — **jamais exécuté automatiquement**. Chaque étape proposée référence un nom d'outil ; si le modèle invente un outil qui n'existe pas, `planner.py` supprime cette référence (`step.tool = None`) plutôt que de faire confiance au modèle.

L'utilisateur choisit lui-même quelles étapes lancer (`Run` par étape dans `/ai`), ce qui appelle le même `POST /api/jobs` que la page Tools — donc la **même validation stricte du Tool Registry** s'applique. Constat en test réel avec le modèle local (`qwen2.5-coder:3b`, 3B) : il propose fréquemment des valeurs d'option légèrement invalides (ex. `"ports": "-T4 -sV -sC -oA nmap_scan"` au lieu d'une vraie liste de ports, `"aggression": "2"` alors que seuls `"1"`/`"3"` sont autorisés) — dans tous les cas observés, `registry.build_command` a rejeté proprement la requête avec un message clair, **avant** tout appel à l'agent Kali. C'est le comportement voulu : l'IA propose, le registre valide, rien d'invalide ne s'exécute.

## AI Assistant (chat)

`POST /api/ai/chat` : question/réponse libre, sans capacité d'exécution — le modèle ne peut que répondre en texte, aucun tool-calling, aucune écriture en base depuis cet endpoint. **Correction Phase 23** : l'affirmation "aucun accès à la base de données" ci-dessus était devenue obsolète dès la Phase 19 sans avoir été corrigée à l'époque — un `project_id` optionnel déclenche bien des lectures réelles (`Project`, `ProjectAISummary`, `AssetChangeEvent`) pour enrichir le system prompt avec la mémoire IA du projet (voir plus bas). Ces lectures restent strictement scopées aux `target_id`/`project_id` explicitement fournis dans la requête — jamais un accès par défaut à un projet non demandé — et aucune écriture n'a lieu. Toujours single-turn, aucun historique de conversation persisté.

## Missions (Phase 18 — autonomie Niveau 2)

Une Mission (`app/models/mission.py`) est un plan approuvé **une fois**, qui exécute ensuite ses étapes l'une après l'autre sans reconfirmation par étape — contrairement au Mission Planner ci-dessus, où chaque `Run` est un clic humain. `MissionOrchestrator.create_mission()` réutilise `AIMissionPlanner` sans modification ; `approve_mission()`/`advance_mission()`/`cancel_mission()` (sync, `app/ai/orchestrator.py`) créent un vrai `Job` par étape via le même `is_executable()` + `prepare_job()` que `POST /api/jobs`/le ticker Phase 14 — jamais un chemin d'exécution parallèle. Autorisation revérifiée à **chaque** étape, jamais seulement à l'approbation. Voir [phase-18-ai-agents.md](phase-18-ai-agents.md) pour l'architecture complète (verrouillage anti-concurrence, isolation Job/Mission, kill switch, niveaux d'autonomie réellement livrés).

## Correlation Agent (Phase 18)

`app/ai/agents/correlation.py::CorrelationAgent`, lecture seule (aucun accès `Session`), propose des liens entre `Finding` que les 3 règles déterministes de la Phase 16 (`app/findings/correlation.py`) ne couvrent pas. Ses suggestions (`POST /api/ai/correlation-suggestions`) sont persistées dans une table dédiée (`AICorrelationSuggestion`, `status: PENDING`) — jamais directement dans `FindingRelation`. Une suggestion ne devient une relation réelle que sur acceptation humaine explicite (`POST /api/ai/correlation-suggestions/{id}/accept`).

## Report Agent (Phase 18)

`app/ai/agents/report.py::ReportAgent`, lecture seule, ne génère jamais un rapport lui-même : `POST /api/ai/reports/propose` renvoie un titre + une liste de scans proposés (`ReportProposal`), que l'utilisateur édite avant de cliquer "Generate" — lequel appelle le `POST /api/reports` existant, inchangé par cette phase.

## AI Memory per Project (Phase 19)

`app/ai/memory.py::regenerate_project_summary()` régénère et persiste un résumé texte du projet (`ProjectAISummary`, table dédiée — jamais un `Finding` de type spécial) après l'activité de scan, jamais recalculé à chaque consultation. Déclenché automatiquement par `execute_job()` (hook isolé, même patron que l'avancement de Mission en Phase 18 : session séparée, ne peut jamais affecter `job.status`), avec un cooldown de 5 minutes ; `POST /api/ai/projects/{id}/summary/regenerate` le contourne pour une régénération manuelle. `GET /api/ai/projects/{id}/summary` renvoie `404` tant qu'aucun résumé n'a jamais été généré.

Les questions temporelles ("qu'est-ce qui a changé depuis le dernier audit ?") sont répondues en enrichissant le chat (`ChatRequest.project_id`) du résumé stocké et des derniers `AssetChangeEvent` (Diff Engine, Phase 14) — une couche de présentation en langage naturel sur des données déjà structurées, jamais un nouveau système de stockage ni un nouvel appel IA de résumé à la volée. Voir [phase-19-ai-memory.md](phase-19-ai-memory.md) pour l'architecture complète.

## Limitations connues

- Pas de mémoire de conversation persistée côté serveur (le contexte du chat vit uniquement dans l'état du frontend) — à revoir avec le modèle `AIConversation`/`AIMessage`, toujours hors de la roadmap numérotée actuelle.
- Le Mission Planner ne connaît pas encore le contexte Projet/Lab (ces entités n'existent pas encore) ; il ne reçoit que `target` et `goal` en texte libre.

## Phase 23 — durcissement sécurité/exécution : aucun changement d'autonomie IA

La Phase 23 (voir [phase-23-security-hardening.md](phase-23-security-hardening.md)) est une phase de consolidation, pas fonctionnelle : **aucun agent, aucun niveau d'autonomie, aucune capacité IA n'a été modifié**. Le seul changement touchant un chemin partagé avec l'IA est la fermeture du bypass d'autorisation sur `POST /api/jobs` (target texte libre) — Missions/Chains passaient déjà par `is_executable()` à chaque étape et n'étaient donc pas concernées par ce bypass. Un audit indépendant mené avant cette phase a vérifié ligne à ligne que Mission reste Niveau 2 (aucun branchement/retry autonome, aucun choix de cible/outil sans re-validation serveur) et qu'aucun composant IA n'atteint Niveau 3/4 — ce constat reste inchangé après la Phase 23.
