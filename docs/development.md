# Développement

## Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/ -v
```

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

- Backend : `pytest` (voir `backend/tests/`).
- Frontend : à ajouter (Vitest / `@nuxt/test-utils`) au fur et à mesure des phases.
