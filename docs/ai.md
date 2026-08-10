# IA locale (Ollama)

CyberLab réutilise l'instance Ollama déjà active sur l'hôte (`host.docker.internal:11434`) — voir [architecture.md](architecture.md). Aucun modèle n'est téléchargé ni géré par CyberLab lui-même.

## Abstraction (`backend/app/ai/`)

```
provider.py   — interface abstraite AIProvider.generate(prompt, system, json_mode) -> str
ollama.py     — OllamaProvider : implémentation concrète (appelle /api/generate)
schemas.py    — AnalysisResult, MissionPlan, MissionStep, ChatMessage/Response
prompts.py    — templates système + construction des prompts
parsing.py    — extraction JSON tolérante (fences markdown, texte parasite)
analyst.py    — AIAnalyst : job de scan -> AnalysisResult
planner.py    — AIMissionPlanner : (target, goal) -> MissionPlan
```

Changer de provider (un autre modèle Ollama, ou plus tard un autre backend) ne touche que `ollama.py` — `analyst.py`/`planner.py` ne dépendent que de l'interface `AIProvider`.

## AI Analyst

`POST /api/ai/analyze/{job_id}` : prend un job terminé (`SUCCESS`/`FAILED`), envoie l'outil/la cible/le résultat parsé/le stdout au modèle avec un prompt qui force une sortie JSON structurée (`{"risk", "summary", "findings", "recommendations", "next_steps"}`, contrainte via l'option Ollama `format: "json"`). Le résultat est persisté sur `Job.ai_analysis` (rejouable, visible dans l'UI sans ré-appeler le modèle). Si la sortie n'est pas un JSON exploitable, `AnalysisResult` retombe proprement sur `risk: "INFO"` avec la réponse brute conservée (`raw_response`) plutôt que de planter.

## AI Mission Planner

`POST /api/ai/plan` : prend `{target, goal}`, transmet au modèle la liste réelle des outils du Tool Registry (nom, description, arguments) et lui demande un plan JSON (`{"steps": [...]}`) — **jamais exécuté automatiquement**. Chaque étape proposée référence un nom d'outil ; si le modèle invente un outil qui n'existe pas, `planner.py` supprime cette référence (`step.tool = None`) plutôt que de faire confiance au modèle.

L'utilisateur choisit lui-même quelles étapes lancer (`Run` par étape dans `/ai`), ce qui appelle le même `POST /api/jobs` que la page Tools — donc la **même validation stricte du Tool Registry** s'applique. Constat en test réel avec le modèle local (`qwen2.5-coder:3b`, 3B) : il propose fréquemment des valeurs d'option légèrement invalides (ex. `"ports": "-T4 -sV -sC -oA nmap_scan"` au lieu d'une vraie liste de ports, `"aggression": "2"` alors que seuls `"1"`/`"3"` sont autorisés) — dans tous les cas observés, `registry.build_command` a rejeté proprement la requête avec un message clair, **avant** tout appel à l'agent Kali. C'est le comportement voulu : l'IA propose, le registre valide, rien d'invalide ne s'exécute.

## AI Assistant (chat)

`POST /api/ai/chat` : question/réponse libre, sans capacité d'exécution — le modèle ne peut que répondre en texte, il n'a accès à aucun outil ni à la base de données depuis cet endpoint.

## Limitations connues

- Pas de mémoire de conversation persistée côté serveur (le contexte du chat vit uniquement dans l'état du frontend) — à revoir avec le modèle `AIConversation`/`AIMessage` (Phase 9+).
- Le Mission Planner ne connaît pas encore le contexte Projet/Lab (ces entités n'existent pas encore) ; il ne reçoit que `target` et `goal` en texte libre.
