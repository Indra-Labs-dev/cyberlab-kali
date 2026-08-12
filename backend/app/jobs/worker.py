import logging

from rq import Worker

from app.core.config import get_settings
from app.intel.sync import start_intel_sync_thread
from app.jobs.queue import get_redis_connection
from app.scheduling.ticker import start_scheduler_thread

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    # Phase 14 -- the Continuous Recon ticker runs as a background thread in
    # this same process rather than a separate service: the worker already
    # has the sync DB + Redis/RQ access it needs. Daemon thread, so it never
    # blocks process shutdown; if the worker container restarts, the thread
    # restarts with it and picks up due schedules from Postgres (next_run_at
    # survives the restart, nothing is held only in memory).
    start_scheduler_thread(get_settings().scheduler_poll_interval_seconds)

    # Phase 15 -- same pattern for EPSS/CISA KEV/NVD background ingestion,
    # a distinct thread since it isn't a Kali tool run (see
    # app/intel/sync.py::start_intel_sync_thread for why it doesn't reuse
    # ScheduledJob).
    start_intel_sync_thread(get_settings().intel_sync_interval_seconds)

    connection = get_redis_connection()
    worker = Worker(["default"], connection=connection)
    worker.work()
