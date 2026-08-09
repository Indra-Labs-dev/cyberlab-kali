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

- `cyberlab-backend` : frontend, api, postgres, redis, worker.
- `cyberlab-kali-net` : api, worker, kali (Phase 2) — isolé du reste pour limiter la surface d'exposition du conteneur d'outils.

## Ollama

Ollama n'est pas conteneurisé. Le backend appelle l'instance déjà active sur l'hôte via `host.docker.internal:11434` (nécessite `extra_hosts: host-gateway`, déjà configuré sur `cyberlab-api`).
