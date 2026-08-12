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

Développement par phases (voir [CHANGELOG.md](CHANGELOG.md)). Phase 17 en cours (Security Graph complète et vérifiée) ; roadmap Phases 13–22 dans [docs/roadmap.md](docs/roadmap.md).

**Fonctionnel de bout en bout, vérifié en conditions réelles :** Projects/Assets (généralisation Phase 13 de Target — type/criticality/tags/technologies/first_seen/last_seen, autorisation comme frontière de sécurité inchangée, voir [docs/phase-13-asset-model.md](docs/phase-13-asset-model.md)), **Continuous Recon** (scans planifiés par intervalle, réutilisant le Job Engine existant — aucun nouveau service) **+ Diff Engine** (détection automatique de changements réseau/technologies/TLS entre deux scans comparables, timeline sur la page Asset, voir [docs/phase-14-continuous-recon.md](docs/phase-14-continuous-recon.md)), **Risk Score explicable** (CVSS + EPSS + CISA KEV + criticité Asset + confidence Finding, formule normalisée et documentée, jamais une boîte noire IA, breakdown complet sur chaque Finding, vue Top Risks, voir [docs/phase-15-risk-score.md](docs/phase-15-risk-score.md)), **Corrélation & Déduplication des Findings** (identité stable par CVE ou titre/port/protocole — jamais de doublon sur un scan répété —, cycle de vie NEW→CONFIRMED→...→REOPENED avec historique complet, 3 règles de corrélation fixes entre outils avec raison lisible, voir [docs/phase-16-correlation-deduplication.md](docs/phase-16-correlation-deduplication.md)), **Security Graph** (Asset/Finding/CVE/Service/Technology reliés par 5 règles fixes avec provenance systématique, traversal récursif borné et cycle-safe sur PostgreSQL — pas de base graphe externe —, visualisation interactive Cytoscape.js sur les pages Asset et Project, voir [docs/phase-17-security-graph.md](docs/phase-17-security-graph.md)), **Tool Registry avec 31 outils curés et testés** (reconnaissance, DNS, web recon/security, SSL/TLS, énumération, OSINT, utilitaires — voir [docs/tools.md](docs/tools.md)) avec profils, niveaux de risque SAFE/CAUTION/RESTRICTED/MANUAL_ONLY et `ai_allowed` réellement appliqué (pas juste affiché), Job Engine avec statut temps réel (WebSocket) et rattachement optionnel à un Project/Asset, terminal interactif confiné au conteneur Kali, Lab Manager (DVWA) piloté via un Docker Socket Proxy plutôt qu'un accès direct à `docker.sock`, IA locale contextualisée (chat, analyse de scan, Mission Planner par tool+profile — jamais d'exécution ni de modification d'autorisation par l'IA elle-même), Tool Health (vérification non destructive par outil), Findings extraits automatiquement, Reports (HTML/Markdown/JSON/PDF), authentification API optionnelle.

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
- [Asset Model (Phase 13)](docs/phase-13-asset-model.md)
- [Continuous Recon + Diff Engine (Phase 14)](docs/phase-14-continuous-recon.md)
- [Risk Intelligence & Risk Score (Phase 15)](docs/phase-15-risk-score.md)
- [Corrélation, Déduplication & Cycle de vie (Phase 16)](docs/phase-16-correlation-deduplication.md)
- [Security Graph (Phase 17)](docs/phase-17-security-graph.md)
- [Roadmap (Phases 13+)](docs/roadmap.md)
