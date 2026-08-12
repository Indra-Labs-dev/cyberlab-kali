from datetime import datetime, timezone

from app.assets.activity import record_asset_activity, technologies_from_whatweb
from app.db.sync_session import get_sync_session
from app.diff.service import generate_change_events
from app.findings.extractor import extract_findings
from app.jobs.kali_client import KaliAgentError, run_tool
from app.jobs.pubsub import publish_job_update
from app.models.finding import Finding
from app.models.job import Job, JobStatus
from app.tools import registry
from app.tools.parsers import parse_output


def run_tool_job(tool: str, args: list[str], timeout: int = 60) -> dict:
    """Executed by the RQ worker; delegates raw execution to the Kali agent."""
    return run_tool(tool, args, timeout=timeout)


def run_registered_tool_job(tool_name: str, params: dict, timeout: int | None = None) -> dict:
    """Validates `params` against the Tool Registry, runs the tool via the Kali
    agent, and parses stdout into a normalized result. Used directly for
    ad-hoc/manual runs; execute_job() wraps this with DB persistence.
    """
    tool = registry.get_tool(tool_name)
    args = registry.build_command(tool_name, params)
    effective_timeout = min(timeout or tool.default_timeout, tool.max_timeout)

    raw = run_tool(tool_name, args, timeout=effective_timeout)
    raw["parsed"] = parse_output(tool.output.parser, raw.get("stdout", ""))
    return raw


def _now() -> datetime:
    return datetime.now(timezone.utc)


def execute_job(job_id: str, tool_name: str, params: dict, timeout: int | None = None) -> None:
    """RQ entrypoint for API-submitted jobs: persists status transitions to
    PostgreSQL and broadcasts each transition over Redis pub/sub so the
    WebSocket layer can push live updates to the frontend.
    """
    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        if job is None or job.status == JobStatus.CANCELLED:
            # Cancelled before the worker even picked it up off the queue.
            return

        job.status = JobStatus.RUNNING
        job.started_at = _now()
        session.commit()
        publish_job_update(job_id, {"id": job_id, "status": JobStatus.RUNNING.value})

        try:
            tool = registry.get_tool(tool_name)
            args = registry.build_command(tool_name, params)
            effective_timeout = min(timeout or tool.default_timeout, tool.max_timeout)
            raw = run_tool(tool_name, args, timeout=effective_timeout)
            parsed = parse_output(tool.output.parser, raw.get("stdout", ""))

            # A concurrent cancel request may have committed CANCELLED while
            # the tool was running; re-read before overwriting the terminal
            # status so a cancellation can never be clobbered by a late result.
            session.refresh(job)
            if job.status == JobStatus.CANCELLED:
                return

            job.stdout = raw.get("stdout")
            job.stderr = raw.get("stderr")
            job.exit_code = raw.get("exit_code")
            job.result = parsed
            job.status = JobStatus.SUCCESS if raw.get("exit_code") == 0 else JobStatus.FAILED
            job.finished_at = _now()

            if job.status == JobStatus.SUCCESS:
                for finding_data in extract_findings(tool_name, job.target, parsed):
                    session.add(Finding(job_id=job.id, **finding_data))

            if job.target_id is not None:
                # The tool actually ran against this asset (whether it
                # succeeded or failed) -- that's real observed activity,
                # distinct from the asset merely being created/edited.
                technologies = (
                    technologies_from_whatweb(parsed)
                    if tool_name == "whatweb" and job.status == JobStatus.SUCCESS
                    else None
                )
                record_asset_activity(session, job.target_id, job.finished_at, technologies)

                # Diff Engine: only meaningful for a job that actually
                # produced a comparable result (SUCCESS) -- a FAILED run
                # (e.g. tool crashed) has nothing to compare.
                if job.status == JobStatus.SUCCESS:
                    generate_change_events(session, job)

            session.commit()
            publish_job_update(
                job_id,
                {
                    "id": job_id,
                    "status": job.status.value,
                    "exit_code": job.exit_code,
                    "result": job.result,
                },
            )
        except (registry.ToolValidationError, registry.ToolNotFoundError, KaliAgentError) as exc:
            session.refresh(job)
            if job.status == JobStatus.CANCELLED:
                return
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.finished_at = _now()
            session.commit()
            publish_job_update(job_id, {"id": job_id, "status": JobStatus.FAILED.value, "error": str(exc)})
        except Exception as exc:
            # Catch-all, deliberately broad: any unexpected error here (an
            # RQ-level JobTimeoutException if job_timeout and the tool's own
            # timeout ever drift apart again, a DB hiccup, anything) must
            # still leave the job in a terminal state. Before this existed,
            # an uncaught exception left the row stuck at RUNNING forever --
            # found via Phase 12 end-to-end testing when RQ's own timeout
            # fired before the tool's timeout did (see jobs.py::create_job).
            try:
                session.refresh(job)
                if job.status != JobStatus.CANCELLED:
                    job.status = JobStatus.FAILED
                    job.error = f"unexpected error: {exc}"
                    job.finished_at = _now()
                    session.commit()
                    publish_job_update(job_id, {"id": job_id, "status": JobStatus.FAILED.value, "error": job.error})
            except Exception:
                pass
            raise
    finally:
        session.close()
