import os

# Force tests onto a dedicated database so the suite can never write rows into
# the real dev/demo database that docker compose containers share. Must run
# before any app module is imported, since Settings()/the async engine are
# cached module-level singletons created on first import.
_base_db = os.environ.get("POSTGRES_DB", "cyberlab")
if not _base_db.endswith("_test"):
    os.environ["POSTGRES_DB"] = f"{_base_db}_test"

import psycopg2  # noqa: E402
import pytest_asyncio  # noqa: E402
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import Base, engine  # noqa: E402
from app.models import Job  # noqa: E402,F401 (register tables on Base.metadata)


def _ensure_test_database_exists() -> None:
    settings = get_settings()
    admin_conn = psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname="postgres",
    )
    admin_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with admin_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{settings.postgres_db}"')
    finally:
        admin_conn.close()


def _create_schema() -> None:
    settings = get_settings()
    from sqlalchemy import create_engine

    sync_engine = create_engine(settings.sync_database_url)
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()


_ensure_test_database_exists()
_create_schema()


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests():
    # Each async test gets its own event loop under pytest-asyncio's default
    # (function-scoped) mode, but the SQLAlchemy async engine + its asyncpg
    # connection pool are created once at import time. Reusing a pooled
    # connection across event loops raises "attached to a different loop".
    # Disposing before each test forces a fresh, loop-bound connection.
    await engine.dispose()
    yield
