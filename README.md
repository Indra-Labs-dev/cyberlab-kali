# CyberLab

CyberLab est un **Cybersecurity Workbench** local pour Kali Linux : une interface web moderne pour lancer des outils de sécurité dans des environnements autorisés/lab, centraliser les résultats et les analyser avec une IA locale (Ollama).

> Destiné à l'apprentissage, aux CTF, au pentest autorisé, à l'audit de vos propres systèmes et au laboratoire de cybersécurité défensive. **Jamais** conçu pour attaquer des systèmes tiers sans autorisation.

## Stack

- **Frontend**: Nuxt 4, Vue 3, TypeScript, Tailwind CSS, xterm.js
- **Backend**: Python 3.12+, FastAPI, SQLAlchemy, Alembic, RQ (job queue)
- **Infra**: Docker Compose, PostgreSQL, Redis, conteneur Kali isolé
- **IA**: Ollama (local, modèle configurable)

Voir [docs/architecture.md](docs/architecture.md) pour le détail.

## Démarrage rapide

```bash
cp .env.example .env
docker compose up -d
```

- Frontend: http://localhost:3300
- API: http://localhost:8300/docs (Swagger UI générée par FastAPI)

```bash
docker compose ps
docker compose logs -f
docker compose down
```

## État du projet

Développement par phases (voir [CHANGELOG.md](CHANGELOG.md)). Phase actuelle : **Phase 9 — Findings + Reports**.

## Documentation

- [Architecture](docs/architecture.md)
- [Développement](docs/development.md)
- [Docker](docs/docker.md)
- [API](docs/api.md)
- [Outils](docs/tools.md)
- [Labs](docs/labs.md)
- [IA](docs/ai.md)
- [Findings & Reports](docs/findings-reports.md)
- [Sécurité](docs/security.md)
