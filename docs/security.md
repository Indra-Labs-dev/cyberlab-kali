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

### Conséquence connue : pas de scan SYN par défaut

`cap_drop: ALL` retire `CAP_NET_RAW`, nécessaire aux scans nmap bas niveau (`-sS`, découverte ARP, etc.). Par défaut, les jobs nmap doivent utiliser des scans applicatifs (`-sT`, TCP connect) qui ne nécessitent pas de socket brut — validé en Phase 2. Si des scans SYN sont nécessaires plus tard, ajouter explicitement `cap_add: [NET_RAW, NET_ADMIN]` au service `cyberlab-kali` est un choix à documenter et justifier (Phase 10 - durcissement), pas un défaut.

## Terminal intégré — surface la plus privilégiée de l'application

```
Nuxt (xterm.js) --WS--> cyberlab-api (relais transparent) --WS interne--> cyberlab-kali (PTY)
```

Contrairement au Job Engine (arguments strictement validés, allowlist d'outils), le terminal donne un **shell interactif complet** — `bash` dans le conteneur `cyberlab-kali`, sans allowlist de commandes. C'est intentionnel (spec section 7) mais cela en fait la surface la plus sensible de CyberLab :

- **Toujours confiné au conteneur Kali** : `cyberlab-api` (`backend/app/api/routes/terminal.py`) ne fait que relayer des frames WebSocket entre le navigateur et l'agent Kali — il n'ouvre jamais lui-même de PTY ni de shell. Le PTY est ouvert par `kali/agent/main.py` (`pty.openpty()` + `subprocess.Popen(["bash"], preexec_fn=os.setsid, ...)`), à l'intérieur du conteneur durci (voir ci-dessus : `cap_drop: ALL`, non-root, pas de `docker.sock`).
- **Authentification interne** : la connexion WebSocket `cyberlab-api → cyberlab-kali` porte le même `KALI_AGENT_TOKEN` que l'exécution d'outils. Testé (`kali/agent/tests/test_terminal_auth.py`) : token manquant, incorrect, ou agent démarré sans `AGENT_TOKEN` configuré → `close(code=4401)` dans les trois cas (pas de repli silencieux vers "auth désactivée").
- **Aucune authentification utilisateur pour l'instant** : n'importe qui atteignant `POST /api/ws/terminal` obtient un shell dans le conteneur Kali. C'est acceptable uniquement parce que CyberLab n'écoute que sur `127.0.0.1` par défaut (section 21). **Avant toute exposition au-delà de localhost, une authentification applicative sur cet endpoint est un prérequis bloquant**, pas une amélioration optionnelle (voir Phase 10).
- **Cycle de vie du processus** : le PTY et le processus `bash` sont fermés/tués (`proc.terminate()` + `proc.wait()`) à la déconnexion — un bug de zombie process (le shell restait `<defunct>` faute de `wait()`) a été trouvé et corrigé pendant les tests de la Phase 6.

## Réseau

- Tous les ports hôte sont bindés sur `127.0.0.1` uniquement.
- Réseau `cyberlab-kali-net` séparé de `cyberlab-backend` : seuls `cyberlab-api` et `cyberlab-worker` peuvent atteindre `cyberlab-kali`.

## Secrets

- Aucun secret en dur dans le code ou committé dans Git (`.env` est dans `.gitignore`).
- `API_SECRET_KEY`, `POSTGRES_PASSWORD`, `KALI_AGENT_TOKEN` générés aléatoirement (`openssl rand -hex`) dans l'environnement de développement local.

## À faire (Phase 10 — durcissement)

- Authentification utilisateur sur l'API si exposée au-delà de `localhost` — **bloquant en particulier pour `/api/ws/terminal`** (shell complet, sans allowlist), voir ci-dessus.
- Audit des dépendances (`pip-audit`, `npm audit`).
- Revue CORS/WebSocket.
- Revue des permissions du conteneur Lab Manager (Phase 7).
