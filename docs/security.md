# Sécurité

## Exécution des outils (conteneur Kali)

L'exécution des commandes ne passe jamais par le shell de l'hôte ni par `docker.sock` :

```
cyberlab-api / cyberlab-worker --(HTTP interne, réseau cyberlab-kali-net)--> cyberlab-kali (agent FastAPI, port 9000)
```

- **Allowlist stricte des exécutables** : `kali/agent/main.py` résout au démarrage le chemin absolu de chaque outil autorisé (`nmap`, `whatweb`, `nikto` pour le MVP) via `shutil.which`. Une requête ne peut jamais désigner un autre binaire — seul un nom logique (`"tool": "nmap"`) est accepté, jamais un chemin.
- **Pas de shell** : `subprocess.run([...], shell=False)` uniquement, arguments passés en liste (jamais de concaténation de chaîne).
- **Validation des arguments** : rejet des métacaractères shell (`; & | \` $ < > \n \r \\`) même si `shell=False` ne les interprète pas — défense en profondeur. Longueur et nombre d'arguments plafonnés. Voir `kali/agent/tests/test_validation.py`.
- **Authentification interne** : un secret partagé (`KALI_AGENT_TOKEN`, généré aléatoirement dans `.env`) est requis en en-tête `X-Agent-Token`. Le conteneur Kali n'est de toute façon accessible que depuis le réseau isolé `cyberlab-kali-net` (api + worker uniquement, aucun port publié sur l'hôte).
- **Timeout obligatoire** : plafonné à 300s côté agent, quel que soit ce que demande l'appelant.
- **Isolation du conteneur** : `cap_drop: ALL`, `security_opt: no-new-privileges`, utilisateur non-root, pas d'accès à `docker.sock`, pas de `privileged: true`, limites mémoire/CPU.

### Conséquence connue : pas de scan SYN par défaut, `-Pn` obligatoire

`cap_drop: ALL` retire `CAP_NET_RAW`, nécessaire aux scans nmap bas niveau (`-sS`, découverte ARP/ICMP, etc.). Par défaut, les jobs nmap utilisent `-sT` (TCP connect, pas de socket brut — validé en Phase 2) **et `-Pn`** (désactive la découverte d'hôte, qui utilise ICMP/ARP par défaut et nécessite donc aussi `CAP_NET_RAW`, indépendamment de `-sT`).

Trouvé en Phase 9 en scannant un vrai lab (DVWA) plutôt que le conteneur Kali lui-même : sans `-Pn`, nmap échoue avec `Couldn't open a raw socket or eth handle` dès la phase de découverte, avant même le scan de ports — ce n'était pas visible plus tôt car les tests précédents ciblaient `cyberlab-kali` depuis lui-même, un cas limite proche du loopback où nmap ne déclenche pas la découverte réseau classique. `-Pn` traite systématiquement la cible comme active et va directement au scan de ports, ce qui est le comportement voulu ici (les cibles sont des conteneurs sur des réseaux Docker contrôlés, pas un scan Internet où "the host might not respond to ping" justifierait une vraie découverte).

Si des scans SYN sont nécessaires plus tard, ajouter explicitement `cap_add: [NET_RAW, NET_ADMIN]` au service `cyberlab-kali` est un choix à documenter et justifier (Phase 10 - durcissement), pas un défaut.

## Terminal intégré — surface la plus privilégiée de l'application

```
Nuxt (xterm.js) --WS--> cyberlab-api (relais transparent) --WS interne--> cyberlab-kali (PTY)
```

Contrairement au Job Engine (arguments strictement validés, allowlist d'outils), le terminal donne un **shell interactif complet** — `bash` dans le conteneur `cyberlab-kali`, sans allowlist de commandes. C'est intentionnel (spec section 7) mais cela en fait la surface la plus sensible de CyberLab :

- **Toujours confiné au conteneur Kali** : `cyberlab-api` (`backend/app/api/routes/terminal.py`) ne fait que relayer des frames WebSocket entre le navigateur et l'agent Kali — il n'ouvre jamais lui-même de PTY ni de shell. Le PTY est ouvert par `kali/agent/main.py` (`pty.openpty()` + `subprocess.Popen(["bash"], preexec_fn=os.setsid, ...)`), à l'intérieur du conteneur durci (voir ci-dessus : `cap_drop: ALL`, non-root, pas de `docker.sock`).
- **Authentification interne** : la connexion WebSocket `cyberlab-api → cyberlab-kali` porte le même `KALI_AGENT_TOKEN` que l'exécution d'outils. Testé (`kali/agent/tests/test_terminal_auth.py`) : token manquant, incorrect, ou agent démarré sans `AGENT_TOKEN` configuré → `close(code=4401)` dans les trois cas (pas de repli silencieux vers "auth désactivée").
- **Aucune authentification utilisateur pour l'instant** : n'importe qui atteignant `POST /api/ws/terminal` obtient un shell dans le conteneur Kali. C'est acceptable uniquement parce que CyberLab n'écoute que sur `127.0.0.1` par défaut (section 21). **Avant toute exposition au-delà de localhost, une authentification applicative sur cet endpoint est un prérequis bloquant**, pas une amélioration optionnelle (voir Phase 10).
- **Cycle de vie du processus** : le PTY et le processus `bash` sont fermés/tués (`proc.terminate()` + `proc.wait()`) à la déconnexion — un bug de zombie process (le shell restait `<defunct>` faute de `wait()`) a été trouvé et corrigé pendant les tests de la Phase 6.

## Lab Manager — le seul service avec accès à `docker.sock`

Le Lab Manager (démarrer/arrêter/reset/supprimer des labs Docker vulnérables-par-design comme DVWA) a besoin de contrôler Docker. C'est en tension directe avec la règle « ne jamais donner `docker.sock` au backend ». Résolution retenue :

- **`docker.sock` n'est monté que dans `cyberlab-labmanager`** (`labmanager/`), un service dédié, minuscule, sans autre rôle. `cyberlab-api` et `cyberlab-worker` n'y ont jamais accès — ils passent par `POST /api/labs/...` sur l'API, qui relaie (`backend/app/api/routes/labs.py`) vers le Lab Manager via HTTP interne authentifié (`LABMANAGER_TOKEN`, même modèle que l'agent Kali).
- **Ce compromis reste un accès quasi-root sur l'hôte** : quiconque compromet `cyberlab-labmanager` peut piloter n'importe quel conteneur du démon Docker hôte, pas seulement les labs. Ajouter `cap_drop`/`no-new-privileges` sur ce service serait un théâtre de sécurité — ces restrictions ne changent rien tant que `docker.sock` est monté. La vraie mitigation est l'isolation fonctionnelle (un seul service étroit, sans exécution de code arbitraire, allowlist stricte des définitions de labs) plutôt que le durcissement du conteneur lui-même.
- **Chaque lab est isolé** : réseau Docker dédié (`cyberlab-lab-<id>`), en plus d'être connecté à `cyberlab-kali-net` pour que le conteneur Kali puisse le scanner par nom. Port hôte publié uniquement sur `127.0.0.1`, port aléatoire (jamais de port fixe qui pourrait entrer en collision ou être deviné).
- **Découverte fiable via labels Docker** : le Lab Manager ne maintient pas d'état dupliqué en base — il interroge Docker directement (`docker ps --filter label=cyberlab.lab=true`), donc pas de désynchronisation possible entre l'état réel des conteneurs et ce que l'UI affiche.
- **Bug trouvé et corrigé pendant les tests de la Phase 7** : les appels du SDK Docker sont synchrones ; les exécuter directement dans un handler FastAPI `async def` bloque tout l'event loop pendant un pull d'image (potentiellement plusieurs minutes) — y compris `/health`, rendant le service entièrement indisponible entre-temps. Corrigé en déportant chaque appel Docker SDK dans un thread (`loop.run_in_executor`).

## IA — l'IA ne peut jamais exécuter d'action directement

Le Mission Planner (`backend/app/ai/planner.py`) **propose** un plan ; il n'appelle jamais `POST /api/jobs` lui-même. C'est le frontend, sur action explicite de l'utilisateur (bouton « Run » par étape), qui déclenche l'exécution — via le même endpoint et donc la **même validation stricte du Tool Registry** que la page Tools (voir [ai.md](ai.md) pour des exemples réels d'options hallucinées par le modèle et rejetées par le registre avant tout appel à l'agent Kali). Un nom d'outil halluciné (qui n'existe pas dans le registre) est explicitement supprimé de l'étape (`step.tool = None`) plutôt que transmis tel quel.

## Réseau

- Tous les ports hôte sont bindés sur `127.0.0.1` uniquement.
- Réseau `cyberlab-kali-net` séparé de `cyberlab-backend` : seuls `cyberlab-api`, `cyberlab-worker`, et les conteneurs de labs (connectés dynamiquement par le Lab Manager) peuvent atteindre `cyberlab-kali`.
- `cyberlab-labmanager` n'est que sur `cyberlab-backend` — pas de raison qu'il touche `cyberlab-kali-net`.

## Secrets

- Aucun secret en dur dans le code ou committé dans Git (`.env` est dans `.gitignore`).
- `API_SECRET_KEY`, `POSTGRES_PASSWORD`, `KALI_AGENT_TOKEN`, `LABMANAGER_TOKEN` générés aléatoirement (`openssl rand -hex`) dans l'environnement de développement local.

## À faire (Phase 10 — durcissement)

- Authentification utilisateur sur l'API si exposée au-delà de `localhost` — **bloquant en particulier pour `/api/ws/terminal`** (shell complet, sans allowlist) et pour `/api/labs` (contrôle indirect de `docker.sock`), voir ci-dessus.
- Audit des dépendances (`pip-audit`, `npm audit`).
- Revue CORS/WebSocket.
