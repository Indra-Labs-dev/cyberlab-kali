from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CyberLab API"
    environment: str = "development"
    api_secret_key: str = "change-me-in-production"
    # Disabled by default: CyberLab binds to 127.0.0.1 only out of the box, so
    # there's no untrusted network path to the API. Set AUTH_ENABLED=true
    # (and a real API_SECRET_KEY) before exposing it beyond localhost — see
    # docs/security.md.
    auth_enabled: bool = False

    postgres_host: str = "cyberlab-postgres"
    postgres_port: int = 5432
    postgres_db: str = "cyberlab"
    postgres_user: str = "cyberlab"
    postgres_password: str = "cyberlab"

    redis_url: str = "redis://cyberlab-redis:6379/0"

    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5-coder:3b"

    cors_origins_raw: str = Field(default="http://localhost:3300", validation_alias="CORS_ORIGINS")

    kali_agent_url: str = "http://cyberlab-kali:9000"
    kali_agent_token: str = "change-me-in-production"
    # Multi-Kali opt-in (roadmap §8) -- comma-separated list of every Kali
    # agent instance to dispatch across, replacing kali_agent_url entirely
    # when set (same "raw string -> list property" shape as
    # cors_origins_raw/cors_origins above). Empty by default: single-
    # instance behavior stays byte-identical to before this existed, and
    # app.jobs.kali_client never touches Redis for selection in that case.
    # See docs/phase-multi-kali.md.
    kali_agent_urls_raw: str = Field(default="", validation_alias="KALI_AGENT_URLS")

    labmanager_url: str = "http://cyberlab-labmanager:9100"
    labmanager_token: str = "change-me-in-production"

    # Phase 14 -- how often the worker's background thread (app/scheduling/
    # ticker.py) checks for due ScheduledJobs. Short enough to keep
    # intervals as low as MIN_INTERVAL_SECONDS meaningful, long enough to
    # not hammer Postgres with an idle stack.
    scheduler_poll_interval_seconds: int = 15

    # Phase 15 -- how often the worker's background thread (app/intel/sync.py)
    # refreshes EPSS/CISA KEV/NVD data. Daily by default (EPSS/KEV are
    # themselves published on a daily cadence); `POST /api/intelligence/sync`
    # triggers an immediate out-of-band run for testing/on-demand use.
    intel_sync_interval_seconds: int = 86400

    # Phase 23 -- how often the worker's background thread
    # (app/jobs/reconciliation.py) sweeps for Jobs stuck at QUEUED/RUNNING
    # with no corresponding RQ entry left in Redis, and how long a Job must
    # have been stuck before the sweep touches it (well past every tool's
    # max_timeout -- must never fire against a job still legitimately
    # running).
    reconciliation_poll_interval_seconds: int = 300
    reconciliation_stuck_after_seconds: int = 1800

    # Post-Phase-23 consolidation (D.2) -- same background thread, a second,
    # much shorter threshold: Mission/ChainRun bookkeeping left stalled by a
    # DB failure between queue.enqueue() succeeding and the orchestrator's
    # own final commit (see app/jobs/reconciliation.py). Unlike the Job
    # threshold above, this isn't bounding how long a *tool* may run -- a
    # step that's genuinely still executing is excluded outright, regardless
    # of age -- it only bounds the brief, normal gap between the
    # orchestrator's two commits.
    reconciliation_orchestration_stuck_after_seconds: int = 300

    # Phase 23 -- minimal Redis-backed rate limiting on sensitive endpoints
    # (job/chain-run creation, report generation, AI calls). Disabled by
    # default, same convention as auth_enabled -- opt in alongside
    # AUTH_ENABLED=true when exposing the instance beyond localhost. One
    # shared window, per-bucket request caps: fixed-window counters via
    # Redis INCR/EXPIRE, not a distributed token-bucket system.
    rate_limit_enabled: bool = False
    rate_limit_window_seconds: int = 60
    rate_limit_job_creation_per_window: int = 30
    rate_limit_chain_run_per_window: int = 20
    rate_limit_report_generation_per_window: int = 10
    rate_limit_ai_call_per_window: int = 20

    # Post-Phase-23 consolidation -- the rate limiter uses its own short,
    # explicit Redis timeout (not app.jobs.queue.get_redis_connection()'s
    # shared, timeout-less singleton used by RQ's worker/pubsub) so a Redis
    # outage fails the dependency fast and deterministically instead of
    # hanging on the OS TCP default.
    rate_limit_redis_timeout_seconds: float = 2.0

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def kali_agent_urls(self) -> list[str]:
        urls = [u.strip() for u in self.kali_agent_urls_raw.split(",") if u.strip()]
        return urls or [self.kali_agent_url]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
