# Multi-Kali (opt-in) — parallélisation des scans

## Périmètre exact (override explicite)

Texte de la roadmap (`docs/roadmap.md`, §8) : « seulement si un utilisateur a réellement besoin de paralléliser des scans longs. Le faire en `docker-compose scale` d'abord (plusieurs conteneurs `cyberlab-kali` identiques derrière un `kali_agent_url` choisi par le worker selon la charge) avant d'imaginer un scheduler distribué complet — 90% de la valeur pour 10% du coût. »

Livré exactement ainsi : plusieurs conteneurs Kali identiques, sélection **côté worker**, **réellement basée sur la charge** (pas un round-robin passif au niveau DNS). Aucun scheduler distribué, aucune infrastructure de monitoring de charge ajoutée à l'agent Kali lui-même — délibérément, pour rester dans le "10% du coût".

## Constat de l'inspection read-only préalable — une dépendance interne révélée

Le worker RQ actuel est **unique et séquentiel** (`app/jobs/worker.py` : un seul `rq.Worker`, traitement d'un Job à la fois, confirmé par le compose file qui ne définit qu'un seul `cyberlab-worker` sans `replicas`). Ajouter des conteneurs Kali seuls, sans pouvoir aussi exécuter plusieurs Jobs en parallèle, n'aurait produit **aucun parallélisme réel** — l'objectif même de cette piste ("paralléliser des scans longs") l'exige. Ce n'est pas une modification d'une piste précédente : c'est une dépendance interne à Multi-Kali, traitée dans son propre périmètre, conformément à la consigne de ne pas la contourner.

Traitement retenu : `docker compose up -d --scale cyberlab-worker=N` fonctionne **sans aucun changement de code** — RQ distribue déjà nativement le travail entre plusieurs processus worker consommant la même queue Redis. Le seul obstacle réel était le `container_name: cyberlab-worker` fixe du compose file, qui empêchait Docker de démarrer plus d'une instance (les noms de conteneur doivent être uniques). Supprimé.

Autre constat de l'inspection : l'agent Kali (`kali/agent/main.py`) n'expose **aucun** endpoint de charge (CPU, nombre d'exécutions en cours, etc.) — seulement `/health` (statut statique) et `/health/tools` (probes non destructifs). En construire un aurait dépassé le "10% du coût" explicitement visé. La charge est donc suivie **côté client** (worker), pas interrogée depuis l'agent.

## Changements

### Backend

- **`Settings.kali_agent_urls_raw`/`kali_agent_urls`** (`app/core/config.py`) : liste optionnelle, comma-separated (même forme que `cors_origins_raw`/`cors_origins`). Vide par défaut → `[kali_agent_url]`, comportement strictement identique à avant.
- **`app/jobs/kali_client.py::_select_agent_url()`** : avec une seule URL configurée, la retourne directement — **aucun appel Redis, aucun appel `/health`**, zéro changement de comportement/performance pour le cas non activé. Avec plusieurs URLs, filtre d'abord les instances qui annoncent réellement l'outil demandé (voir "Post-audit fix" ci-dessous), puis choisit parmi elles celle dont le compteur "busy" Redis (`cyberlab:kali:busy:{url}`) est le plus bas. Ce compteur est incrémenté **avant** l'appel HTTP réel et décrémenté dans un `finally` (donc y compris en cas d'échec/timeout) — un signal de charge réel et vérifiable, jamais une supposition.
- `get_tool_health()` reste volontairement scopé à `kali_agent_url` (l'instance primaire) uniquement : c'est un endpoint de diagnostic humain (non utilisé par le dispatch de Jobs, ni exposé au frontend), pas une source de vérité pour la sélection — documenté comme simplification assumée, sans lien avec la correction ci-dessous.

### Post-audit fix — Multi-Kali × Plugin System (compatibilité d'outils par instance)

Un audit read-only ultérieur a révélé que l'hypothèse initiale de `_select_agent_url()` (« tous les réplicas exécutent la même image, donc la disponibilité des outils est identique par construction ») restait vraie pour les 31 outils curatés, mais **cassée par construction** dès que Plugin System (`EXTRA_ALLOWED_TOOLS`) est utilisé conjointement : ce réglage se configure par conteneur, pas dans l'image partagée. Un outil plugin disponible seulement sur `kali-1` pouvait être routé vers `kali-2` (choisi par charge, aveuglément), provoquant un échec de Job non-déterministe selon l'instance tirée au sort par le compteur de charge — jamais testé par aucune des deux pistes individuellement.

**Correctif** : `_select_agent_url()` interroge désormais `GET {url}/health` (endpoint déjà existant, non authentifié, aucune nouvelle infrastructure) pour chaque instance configurée, filtre celles qui annoncent réellement l'outil demandé dans `tools_available`, puis applique la sélection par charge **uniquement parmi les instances compatibles**. Une instance injoignable pendant cette vérification est traitée comme incompatible (exclue, pas fatale). Si aucune instance ne supporte l'outil, une `KaliAgentError` déterministe est levée (`"no configured Kali agent instance has tool {tool!r} available"` — ne fuite ni token ni URL). Pour les 31 outils curatés (présents partout par construction), ce filtre est un no-op : la sélection par charge reste identique à avant. Cas mono-instance : totalement inchangé, aucun appel `/health` supplémentaire.

### Infrastructure (`docker-compose.yml`)

- `container_name` fixe supprimé sur `cyberlab-kali` **et** `cyberlab-worker` — sans ce changement, ni le scaling du worker (nécessaire pour un parallélisme réel) ni l'ajout d'un second Kali n'étaient possibles. Aucun effet par défaut (`docker compose up -d` sans option continue de démarrer exactement une instance de chaque, Docker attribue juste un nom généré).
- Second service Kali (`cyberlab-kali-2`) ajouté **en commentaire**, désactivé par défaut, copie exacte de la posture de sécurité de `cyberlab-kali` (`cap_drop: ALL`, `cap_add: [NET_RAW]`, `no-new-privileges`, limites mémoire/CPU, réseau `cyberlab-kali-net` uniquement). Un `--scale cyberlab-kali=N` seul aurait donné des réplicas partageant le même nom DNS (résolution round-robin par Docker, non individuellement adressable par le worker) — insuffisant pour une sélection "par la charge" réelle, d'où des blocs de service explicitement nommés plutôt que `--scale` pour ce service précis.
- `.env.example` documente `KALI_AGENT_URLS`.

## Ce qui n'est délibérément pas fait

- **Aucun scheduler distribué.** Explicitement exclu par le texte de la roadmap lui-même.
- **Aucun endpoint de charge sur l'agent Kali.** La charge suivie est "nombre d'appels actuellement en vol depuis ce backend", pas une métrique système réelle (CPU/mémoire) — un signal honnête mais approximatif, cohérent avec "10% du coût".
- **Pas de `--scale cyberlab-kali=N` comme mécanisme principal**, pour la raison d'adressabilité DNS expliquée ci-dessus.
- **`get_tool_health()` non étendu** à agréger tous les réplicas — reste un endpoint de diagnostic humain, distinct du chemin de dispatch (voir "Post-audit fix" ci-dessus, qui corrige spécifiquement ce dernier).

## Vérification en conditions réelles (Docker, 2 vraies instances Kali)

1. `docker compose up -d --scale cyberlab-worker=2` : confirmé fonctionnel après suppression de `container_name`, sans aucun changement de code — 2 processus `cyberlab-worker` réellement démarrés, RQ les répartissant nativement. Remis à 1 après vérification.
2. Second conteneur Kali réel démarré (image identique, mêmes options de sécurité), joint à `cyberlab-kali-net`, healthcheck `/health` confirmé.
3. `run_tool()` appelé pour de vrai (dans le conteneur `cyberlab-api`, `KALI_AGENT_URLS` pointant vers les deux instances réelles) : séquentiellement, les deux instances étant toujours à charge égale (0), le choix reste stable sur la première — comportement correct, pas un bug. Pour prouver la sélection **par charge réelle**, deux appels concurrents ont été déclenchés (threads Python réels, cible volontairement injoignable pour forcer un nmap réellement en vol plusieurs secondes) : pendant que le premier appel était réellement en cours sur `cyberlab-kali-1` (compteur Redis confirmé à 1), le second a correctement choisi l'instance idle (`cyberlab-kali-2`) — preuve directe, pas déduite, que la sélection réagit à une charge réelle et pas à un round-robin aveugle. Compteurs revenus à 0 après complétion.
4. Environnement entièrement restauré à son état par défaut (1 worker, 1 Kali, aucune variable `KALI_AGENT_URLS`) après vérification — aucun fichier suivi modifié pendant le test lui-même (le second conteneur a été démarré via `docker run` ad hoc, jamais via `docker-compose.yml`/`.env`).
5. **Post-audit fix** : second conteneur Kali ad hoc démarré avec `EXTRA_ALLOWED_TOOLS=myplugin:echo` (donc seul à avoir `myplugin`), l'autre instance restant par défaut. Compteurs Redis manipulés pour que l'instance *sans* `myplugin` paraisse délibérément la moins chargée — `run_tool('myplugin', ...)` appelé 3 fois réellement depuis le conteneur `cyberlab-api` : toujours routé vers la seule instance compatible, jamais vers celle "moins chargée" mais incompatible. `run_tool('nmap', ...)` (outil curaté, présent partout) : toujours un succès, sélection par charge inchangée. `run_tool('nowhere-tool', ...)` (absent des deux instances) : `KaliAgentError` déterministe, pas un choix aléatoire. Conteneur ad hoc supprimé après vérification, `git status` confirmé propre.

## Tests

`backend/tests/jobs/test_kali_client.py` (13 tests) : cas mono-URL ne touche jamais Redis ni `/health`, sélection choisit réellement l'instance la moins chargée parmi les compatibles, compteur absent traité comme zéro, incrémentation confirmée **avant** l'appel HTTP (empêche une course où deux sélections concurrentes convergeraient sur la même instance), décrémentation garantie même en cas d'échec de l'agent, erreurs HTTP toujours enveloppées en `KaliAgentError` — plus (post-audit fix) : une instance sans le plugin est exclue même si elle est moins chargée, sélection par charge préservée quand le plugin est partout, erreur déterministe si aucune instance ne convient, comportement d'un outil curaté inchangé de bout en bout via `run_tool()`, message d'erreur sans fuite de token/URL, une instance injoignable pendant la vérification est traitée comme incompatible plutôt que fatale.

## Migration

Aucune. Uniquement de la configuration (`Settings`) et de l'infrastructure (compose).
