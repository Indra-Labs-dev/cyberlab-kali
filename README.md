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

Développement par phases (voir [CHANGELOG.md](CHANGELOG.md)). Les 10 phases sont complètes.

**Fonctionnel de bout en bout, vérifié en conditions réelles :** Tool Registry (nmap/whatweb/nikto), Job Engine avec statut temps réel (WebSocket), terminal interactif confiné au conteneur Kali, Lab Manager (DVWA), IA locale (chat, analyse de scan, Mission Planner), Findings extraits automatiquement, Reports (HTML/Markdown/JSON/PDF), authentification API optionnelle.

**Écart connu par rapport à la liste de succès initiale :** pas de modèle `Project`/`Target` dédié — un job prend directement une cible en texte libre. Les pages Projects/Targets existent dans la navigation mais affichent un état « pas encore implémenté » explicite plutôt que des données factices (voir `frontend/app/pages/{projects,targets}/index.vue`).

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
