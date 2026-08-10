from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ai, health, jobs, labs, terminal, tools, ws
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

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
