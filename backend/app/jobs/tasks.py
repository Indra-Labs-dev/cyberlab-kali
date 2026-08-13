import hashlib
import logging
from datetime import datetime, timezone

from app.assets.activity import record_asset_activity, technologies_from_whatweb
from app.db.sync_session import get_sync_session
from app.diff.service import generate_change_events
from app.findings.correlation import correlate_asset_findings
from app.findings.extractor import extract_findings
from app.findings.service import upsert_finding
from app.graph.builder import build_graph_for_asset
from app.jobs.kali_client import KaliAgentError, run_tool
from app.jobs.pubsub import publish_job_update
from app.models.asset import Asset
from app.models.job import Job, JobStatus
from app.risk.service import seed_cvss_from_tool
from app.tools import registry
from app.tools.parsers import parse_output
from app.tools.parsers.nuclei import cvss_hints

logger = logging.getLogger("cyberlab.jobs.tasks")


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
    try:
        _execute_job(job_id, tool_name, params, timeout)
    finally:
        # Phase 18: outermost finally, so this runs after the job's own
        # session (below) has already closed and its terminal status
        # already committed -- including on the outer `except Exception:
        # ... raise` path, where code placed *after* (rather than in a
        # finally wrapping) the try/finally below would never run. A brand
        # new session, fully isolated try/except: a bug here can never
        # mutate `job.status` or turn a successful Job back into a failure.
        try:
            from app.ai.orchestrator import advance_mission_for_job  # local: avoids a tasks<->orchestrator import cycle

            advance_mission_for_job(job_id)
        except Exception:
            logger.exception("mission advancement failed for job %s", job_id)

        # Phase 19: same isolation reasoning as the Mission hook above --
        # an LLM call is slow/network-bound (10-30s observed with the
        # local Ollama model), so it never shares the job's own
        # transaction/session, and a failure here can never affect
        # job.status either. Separate try/except so a bug in one hook can
        # never suppress the other.
        try:
            from app.ai.memory import regenerate_project_summary_for_job  # local: avoids a tasks<->memory import cycle

            regenerate_project_summary_for_job(job_id)
        except Exception:
            logger.exception("project summary regeneration failed for job %s", job_id)

        # Phase 21 -- same isolation reasoning as the Mission hook above:
        # advancing a chain run means *creating a new Job*, the same
        # "next-job-creation" concern Phase 18 already isolated from this
        # job's own transaction. A bug in condition evaluation or Job
        # creation here can never flip this Job back to FAILED.
        try:
            from app.chains.service import advance_chain_run_for_job  # local: avoids a tasks<->chains import cycle

            advance_chain_run_for_job(job_id)
        except Exception:
            logger.exception("chain run advancement failed for job %s", job_id)


def _execute_job(job_id: str, tool_name: str, params: dict, timeout: int | None = None) -> None:
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
            # Phase 20 -- minimal integrity proof, computed inline (not an
            # isolated post-completion hook like Mission/Memory, Phase
            # 18/19): unlike those, this is a local, synchronous, no-network
            # computation over data already in memory, so it belongs in the
            # same transaction as the rest of this block, not split out.
            # Never None when stdout itself isn't -- computed unconditionally
            # here regardless of exit code, so both SUCCESS and
            # FAILED-by-exit-code jobs get one; only the two exception
            # handlers below (tool never actually ran) leave it NULL, since
            # there is no stdout to prove the integrity of.
            if job.stdout is not None:
                job.evidence_sha256 = hashlib.sha256(job.stdout.encode("utf-8")).hexdigest()
            job.status = JobStatus.SUCCESS if raw.get("exit_code") == 0 else JobStatus.FAILED
            job.finished_at = _now()

            if job.status == JobStatus.SUCCESS:
                if tool_name == "nuclei":
                    # CVSS nuclei's own templates already carry (see
                    # app/tools/parsers/nuclei.py::cvss_hints) is reused
                    # immediately -- no need to wait for the next NVD sync,
                    # and sync_nvd_cvss() will skip any CVE seeded here.
                    # Seeded *before* upsert_finding so a brand-new
                    # Finding's first Risk Score recalculation already sees it.
                    seed_cvss_from_tool(session, cvss_hints(parsed))

                # Phase 16: deduplicates against any existing Finding
                # sharing the same signature (same asset+CVE, or same
                # asset+normalized-title+port/protocol) instead of always
                # creating a new row -- see app/findings/service.py. Risk
                # Score (Phase 15) is recomputed inside upsert_finding
                # itself, only when something risk-relevant actually
                # changed.
                for finding_data in extract_findings(tool_name, job.target, parsed):
                    upsert_finding(session, job, finding_data)

                if job.target_id is not None:
                    # Cross-tool correlation (Phase 16) -- explicit, fixed
                    # rules over this asset's findings only, not a global pass.
                    correlate_asset_findings(session, job.target_id)

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

                    # Security Graph (Phase 17): rebuilt from this asset's
                    # current Findings/technologies/relations -- after
                    # record_asset_activity above so a technology just
                    # observed by this job is already reflected. Idempotent,
                    # never a duplicate edge on repeated scans.
                    asset = session.get(Asset, job.target_id)
                    if asset is not None:
                        build_graph_for_asset(session, asset)

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
