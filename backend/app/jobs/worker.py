import logging
from datetime import timedelta

from rq import Worker

from app.core.config import get_settings
from app.intel.sync import start_intel_sync_thread
from app.jobs.queue import get_redis_connection
from app.jobs.reconciliation import start_reconciliation_thread
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

    # Phase 23 -- same pattern again: a Job stuck at QUEUED/RUNNING with no
    # corresponding RQ entry left in Redis (Redis restart, worker crash
    # mid-execution) is otherwise invisible and stays stuck forever. Post-
    # Phase-23 consolidation (D.2) folded a second, independent sweep into
    # the same thread: Mission/ChainRun bookkeeping left stalled by a DB
    # failure between queue.enqueue() succeeding and the orchestrator's own
    # final commit -- see app/jobs/reconciliation.py's module docstring.
    start_reconciliation_thread(
        get_settings().reconciliation_poll_interval_seconds,
        stuck_after=timedelta(seconds=get_settings().reconciliation_stuck_after_seconds),
        orchestration_stuck_after=timedelta(seconds=get_settings().reconciliation_orchestration_stuck_after_seconds),
    )

    connection = get_redis_connection()
    worker = Worker(["default"], connection=connection)
    worker.work()
