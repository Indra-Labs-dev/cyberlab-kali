# Architecture

## Vue d'ensemble

```
Nuxt (frontend, :3300) --REST/WS--> FastAPI (api, :8300) --+--> PostgreSQL (:55432)
                                                            +--> Redis (:63790) <--> Worker RQ
                                                            +--> Kali container (réseau isolé cyberlab-kali-net)
                                                            +--> Ollama (hôte, :11434)
```

## Services Docker Compose

| Service | Rôle | Réseau(x) | Port hôte |
|---|---|---|---|
| `cyberlab-frontend` | Nuxt 4 UI | cyberlab-backend | 3300 |
| `cyberlab-api` | FastAPI (REST + WebSocket) | cyberlab-backend, cyberlab-kali-net | 8300 |
| `cyberlab-worker` | Worker RQ (exécution des jobs d'outils) | cyberlab-backend, cyberlab-kali-net | — |
| `cyberlab-postgres` | Persistance | cyberlab-backend | 55432 |
| `cyberlab-redis` | File de jobs / pub-sub | cyberlab-backend | 63790 |
| `cyberlab-kali` | Outils de sécurité, isolé | cyberlab-kali-net | — |

Ollama n'est **pas** conteneurisé : le backend réutilise l'instance Ollama déjà active sur l'hôte Kali (`host.docker.internal:11434`), pour ne pas dupliquer la VRAM/RAM (contrainte mémoire de la machine de développement).

## Décisions architecturales

- **File de jobs : RQ plutôt que Celery.** Plus léger (pas de broker AMQP séparé), suffisant pour des jobs d'outils CLI séquentiels/parallèles, cohérent avec Redis déjà présent dans la stack.
- **Aucun accès à `docker.sock` depuis l'API/worker.** Le Lab Manager et le conteneur Kali sont pilotés via des mécanismes explicites (API Docker via SDK dédié avec permissions limitées, à définir en Phase 7), jamais via montage du socket Docker hôte dans un conteneur applicatif.
- **Ports hôte remappés** (3300/8300/55432/63790) pour cohabiter avec d'autres stacks Docker locales utilisant les ports par défaut.
- **Tool Registry déclaratif (YAML)** : chaque outil Kali est décrit par un fichier de définition (exécutable, arguments typés/validés, parser de sortie), jamais codé en dur côté frontend. Voir [tools.md](tools.md).
