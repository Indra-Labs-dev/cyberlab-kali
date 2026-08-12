from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    ai,
    assets,
    findings,
    graph,
    health,
    intelligence,
    jobs,
    labs,
    projects,
    reports,
    schedules,
    targets,
    terminal,
    tools,
    ws,
)
from app.core.auth_middleware import BearerTokenAuthMiddleware
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

# Middleware added last wraps outermost, so CORS headers are still attached
# to 401 responses from the auth layer below it.
app.add_middleware(BearerTokenAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(ws.router, prefix="/api")
app.include_router(terminal.router, prefix="/api")
app.include_router(labs.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(findings.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(targets.router, prefix="/api")
app.include_router(assets.router, prefix="/api")
app.include_router(schedules.router, prefix="/api")
app.include_router(intelligence.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
