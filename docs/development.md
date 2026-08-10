# Développement

## Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
POSTGRES_HOST=localhost POSTGRES_PORT=55432 .venv/bin/pytest tests/ -v
```

`POSTGRES_HOST`/`POSTGRES_PORT` point pytest at the Postgres exposed by `docker compose` on the host (`127.0.0.1:55432` by default). `backend/tests/conftest.py` automatically redirects to a separate `<POSTGRES_DB>_test` database and creates it if missing — the test suite never writes into the dev database the containers use.

En développement dans Docker, le code n'est pas monté en volume (build multi-stage classique) : après une modification, reconstruire le service concerné :

```bash
docker compose up -d --build cyberlab-api
```

## Frontend (Nuxt 4)

```bash
cd frontend
npm install
npm run dev
```

## Migrations (Alembic)

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "message"
.venv/bin/alembic upgrade head
```

## Tests

- Backend : `pytest backend/tests/`.
- Agent Kali : `pytest kali/agent/tests/`.
- Lab Manager : `pytest labmanager/tests/`.
- **Exécuter ces trois suites séparément**, pas dans une seule commande `pytest` combinée : `kali/agent/tests/` et `labmanager/tests/` sont chacun un package nommé `tests`, ce qui provoque une collision d'import si on les collecte ensemble. Cohérent avec le fait que ce sont des services déployés indépendamment (images Docker séparées).
- Frontend : à ajouter (Vitest / `@nuxt/test-utils`) au fur et à mesure des phases.
