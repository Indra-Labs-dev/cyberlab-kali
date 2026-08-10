# Docker

## Démarrer / arrêter

```bash
cp .env.example .env   # une seule fois, puis ajuster les secrets
docker compose up -d
docker compose ps
docker compose logs -f
docker compose down
```

`docker compose down` conserve les volumes (`cyberlab-postgres-data`, `cyberlab-redis-data`) : les données survivent à un redémarrage. Pour repartir de zéro (destructif) : `docker compose down -v`.

## Ports hôte

Les ports par défaut de Postgres/Redis/8000/3000 étaient déjà occupés par une autre stack Docker locale sur cette machine. CyberLab expose donc :

| Service | Port hôte | Variable |
|---|---|---|
| Frontend | 3300 | `FRONTEND_PORT` |
| API | 8300 | `API_PORT` |
| PostgreSQL | 55432 | `POSTGRES_PORT` |
| Redis | 63790 | `REDIS_PORT` |

Tous les ports sont bindés sur `127.0.0.1` uniquement (pas d'exposition réseau externe par défaut).

## Réseaux

- `cyberlab-backend` : frontend, api, postgres, redis, worker, labmanager.
- `cyberlab-kali-net` : api, worker, kali, + les conteneurs de labs (connectés dynamiquement) — isolé du reste pour limiter la surface d'exposition du conteneur d'outils.
- Les noms de ces deux réseaux sont épinglés (`name:` explicite dans `docker-compose.yml`) plutôt que laissés au préfixage automatique de Compose, car le Lab Manager doit pouvoir s'y connecter dynamiquement par un nom stable et connu à l'avance (`KALI_NETWORK_NAME`).
- Chaque lab créé par le Lab Manager obtient en plus son propre réseau dédié (`cyberlab-lab-<id>`), supprimé automatiquement quand le lab est supprimé.

## Services

| Service | Rôle |
|---|---|
| `cyberlab-frontend` | Nuxt UI |
| `cyberlab-api` | FastAPI (REST + WebSocket) |
| `cyberlab-worker` | Worker RQ (exécution des jobs) |
| `cyberlab-kali` | Outils de sécurité (nmap/whatweb/nikto) + terminal PTY |
| `cyberlab-labmanager` | Cycle de vie des labs Docker — seul service avec `docker.sock` |
| `cyberlab-postgres` / `cyberlab-redis` | Persistance / file de jobs |

## Ollama

Ollama n'est pas conteneurisé. Le backend appelle l'instance déjà active sur l'hôte via `host.docker.internal:11434` (nécessite `extra_hosts: host-gateway`, déjà configuré sur `cyberlab-api`).
