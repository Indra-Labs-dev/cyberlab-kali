"""Phase 21 -- proves execute_job() and chain-run advancement are wired
together correctly and safely: a real Job finishing SUCCESS triggers a
real chain advancement, and a failure in that hook can never affect the
Job's own already-committed status. Mirrors
tests/jobs/test_mission_integration.py's structure/reasoning.
"""

import uuid
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from app.chains.service import create_chain_run
from app.db.sync_session import get_sync_session
from app.jobs.tasks import execute_job
from app.models.asset import Asset, AssetType, AuthorizationStatus
from app.models.job import Job, JobStatus
from app.models.mission_template import (
    ChainConditionType,
    ChainRunStep,
    ChainRunStepStatus,
    MissionTemplate,
    MissionTemplateStep,
)
from app.models.project import Project


def _make_two_step_template_and_asset() -> tuple[str, str]:
    session = get_sync_session()
    try:
        project = Project(id=uuid.uuid4(), name="Chain Integration Fixture")
        session.add(project)
        session.flush()
        asset = Asset(
            id=uuid.uuid4(), project_id=project.id, name="kali", hostname="cyberlab-kali", type=AssetType.CONTAINER,
            authorization_status=AuthorizationStatus.LAB,
        )
        session.add(asset)
        session.flush()

        template = MissionTemplate(id=uuid.uuid4(), name="nmap then whatweb")
        session.add(template)
        session.flush()
        session.add(MissionTemplateStep(id=uuid.uuid4(), template_id=template.id, step_order=0, tool="nmap", profile="quick_scan"))
        session.add(
            MissionTemplateStep(
                id=uuid.uuid4(), template_id=template.id, step_order=1, tool="whatweb", profile="basic_fingerprint",
                condition_type=ChainConditionType.PORT_OPEN, condition_params={"ports": [80, 443]},
            )
        )
        session.commit()
        return str(template.id), str(asset.id)
    finally:
        session.close()


def _get_steps(run_id) -> list[ChainRunStep]:
    session = get_sync_session()
    try:
        session.expire_on_commit = False
        return list(
            session.execute(select(ChainRunStep).where(ChainRunStep.chain_run_id == run_id).order_by(ChainRunStep.step_order)).scalars()
        )
    finally:
        session.close()


def test_execute_job_success_advances_chain_run_to_next_step():
    template_id, asset_id = _make_two_step_template_and_asset()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
    steps = _get_steps(run.id)
    job_id = str(steps[0].job_id)
    assert steps[0].status == ChainRunStepStatus.QUEUED

    nmap_xml_open_port_80 = (
        '<?xml version="1.0"?><nmaprun><host><status state="up"/>'
        '<address addr="10.0.0.1" addrtype="ipv4"/>'
        '<ports><port protocol="tcp" portid="80"><state state="open"/></port></ports>'
        "</host></nmaprun>"
    )

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": nmap_xml_open_port_80, "stderr": "", "exit_code": 0}):
        with patch("app.chains.service.get_queue", return_value=MagicMock()) as mock_get_queue:
            execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.SUCCESS
    finally:
        session.close()

    # The post-completion hook must have reconciled step 1 to SUCCESS,
    # evaluated step 2's PORT_OPEN condition against the real parsed nmap
    # result, and queued it -- with no explicit advance call from this test.
    steps = _get_steps(run.id)
    assert steps[0].status == ChainRunStepStatus.SUCCESS
    assert steps[1].status == ChainRunStepStatus.QUEUED
    assert steps[1].job_id is not None
    mock_get_queue.return_value.enqueue.assert_called_once()


def test_job_stays_success_even_if_chain_advancement_fails():
    template_id, asset_id = _make_two_step_template_and_asset()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
    steps = _get_steps(run.id)
    job_id = str(steps[0].job_id)

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 0}):
        with patch("app.chains.service.advance_chain_run_for_job", side_effect=RuntimeError("boom")):
            # execute_job() must not raise even though the chain hook blew
            # up -- swallowed (and logged) by its own isolated try/except.
            execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    session = get_sync_session()
    try:
        job = session.get(Job, job_id)
        assert job.status == JobStatus.SUCCESS
        assert job.exit_code == 0
    finally:
        session.close()

    # The step never got reconciled (the hook that would have done it
    # raised before touching the DB) -- still QUEUED.
    steps = _get_steps(run.id)
    assert steps[0].status == ChainRunStepStatus.QUEUED


def test_chain_hook_independent_of_mission_and_memory_hooks():
    """A failure in the Mission (Phase 18) or Memory (Phase 19) hook must
    never suppress the chain-run hook, and vice versa -- all three are
    separate try/except blocks in execute_job()'s finally."""
    template_id, asset_id = _make_two_step_template_and_asset()

    with patch("app.chains.service.get_queue", return_value=MagicMock()):
        run = create_chain_run(uuid.UUID(template_id), uuid.UUID(asset_id))
    steps = _get_steps(run.id)
    job_id = str(steps[0].job_id)

    with patch("app.jobs.tasks.run_tool", return_value={"stdout": "", "stderr": "", "exit_code": 1}):
        with patch("app.ai.orchestrator.advance_mission_for_job", side_effect=RuntimeError("mission hook boom")):
            with patch("app.ai.memory.regenerate_project_summary_for_job", side_effect=RuntimeError("memory hook boom")):
                with patch("app.chains.service.get_queue", return_value=MagicMock()):
                    execute_job(job_id, "nmap", {"target": "cyberlab-kali"}, 60)

    # exit_code=1 -> nmap step FAILED -> chain run FAILED -- but the point
    # here is that the hook still RAN (reconciled the step) despite the
    # other two hooks blowing up first in the same finally block.
    steps = _get_steps(run.id)
    assert steps[0].status == ChainRunStepStatus.FAILED
