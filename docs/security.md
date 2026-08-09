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

## Réseau

- Tous les ports hôte sont bindés sur `127.0.0.1` uniquement.
- Réseau `cyberlab-kali-net` séparé de `cyberlab-backend` : seuls `cyberlab-api` et `cyberlab-worker` peuvent atteindre `cyberlab-kali`.

## Secrets

- Aucun secret en dur dans le code ou committé dans Git (`.env` est dans `.gitignore`).
- `API_SECRET_KEY`, `POSTGRES_PASSWORD`, `KALI_AGENT_TOKEN` générés aléatoirement (`openssl rand -hex`) dans l'environnement de développement local.

## À faire (Phase 10 — durcissement)

- Authentification utilisateur sur l'API si exposée au-delà de `localhost`.
- Audit des dépendances (`pip-audit`, `npm audit`).
- Revue CORS/WebSocket.
- Revue des permissions du conteneur Lab Manager (Phase 7).
