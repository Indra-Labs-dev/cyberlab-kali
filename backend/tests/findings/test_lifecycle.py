import uuid

import pytest
from sqlalchemy import select

from app.db.sync_session import get_sync_session
from app.findings.lifecycle import InvalidTransitionError, is_valid_transition, maybe_auto_reopen, transition_status
from app.models.finding import Finding, FindingStatus, Severity
from app.models.finding_relation import FindingStatusHistory
from app.models.job import Job, JobStatus


def _make_finding(status: FindingStatus = FindingStatus.NEW) -> Finding:
    session = get_sync_session()
    try:
        job = Job(id=uuid.uuid4(), tool="nmap", target="x", params={}, status=JobStatus.SUCCESS)
        session.add(job)
        session.commit()

        finding = Finding(
            job_id=job.id,
            target="x",
            source_tool="nmap",
            title="t",
            description="",
            severity=Severity.MEDIUM,
            evidence={},
            status=status,
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        return finding
    finally:
        session.close()


@pytest.mark.parametrize(
    "old,new,expected",
    [
        (FindingStatus.NEW, FindingStatus.CONFIRMED, True),
        (FindingStatus.NEW, FindingStatus.IN_REVIEW, False),
        (FindingStatus.NEW, FindingStatus.REMEDIATED, False),
        (FindingStatus.CONFIRMED, FindingStatus.IN_REVIEW, True),
        (FindingStatus.CONFIRMED, FindingStatus.NEW, False),
        (FindingStatus.IN_REVIEW, FindingStatus.ACCEPTED_RISK, True),
        (FindingStatus.IN_REVIEW, FindingStatus.FALSE_POSITIVE, True),
        (FindingStatus.IN_REVIEW, FindingStatus.REMEDIATED, True),
        (FindingStatus.IN_REVIEW, FindingStatus.NEW, False),
        (FindingStatus.ACCEPTED_RISK, FindingStatus.REOPENED, True),
        (FindingStatus.ACCEPTED_RISK, FindingStatus.CONFIRMED, False),
        (FindingStatus.FALSE_POSITIVE, FindingStatus.REOPENED, True),
        (FindingStatus.REMEDIATED, FindingStatus.REOPENED, True),
        (FindingStatus.REOPENED, FindingStatus.CONFIRMED, True),
        (FindingStatus.REOPENED, FindingStatus.IN_REVIEW, True),
        (FindingStatus.REOPENED, FindingStatus.ACCEPTED_RISK, False),
        (FindingStatus.NEW, FindingStatus.NEW, False),
    ],
)
def test_is_valid_transition_matrix(old, new, expected):
    assert is_valid_transition(old, new) is expected


def test_transition_status_applies_and_records_history():
    finding = _make_finding(FindingStatus.NEW)
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        transition_status(session, finding, FindingStatus.CONFIRMED, reason="manual review", triggered_by="manual")
        session.commit()

        assert finding.status == FindingStatus.CONFIRMED
        history = session.execute(
            select(FindingStatusHistory).where(FindingStatusHistory.finding_id == finding.id)
        ).scalar_one()
        assert history.old_status == FindingStatus.NEW
        assert history.new_status == FindingStatus.CONFIRMED
        assert history.reason == "manual review"
        assert history.triggered_by == "manual"
    finally:
        session.close()


def test_transition_status_rejects_invalid_transition_and_changes_nothing():
    finding = _make_finding(FindingStatus.NEW)
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        with pytest.raises(InvalidTransitionError):
            transition_status(session, finding, FindingStatus.REMEDIATED, reason=None, triggered_by="manual")
        session.rollback()

        refreshed = session.get(Finding, finding.id)
        assert refreshed.status == FindingStatus.NEW
        count = session.execute(
            select(FindingStatusHistory).where(FindingStatusHistory.finding_id == finding.id)
        ).scalars().all()
        assert count == []
    finally:
        session.close()


@pytest.mark.parametrize(
    "status,should_reopen",
    [
        (FindingStatus.REMEDIATED, True),
        (FindingStatus.FALSE_POSITIVE, True),
        (FindingStatus.ACCEPTED_RISK, False),
        (FindingStatus.NEW, False),
        (FindingStatus.CONFIRMED, False),
        (FindingStatus.IN_REVIEW, False),
        (FindingStatus.REOPENED, False),
    ],
)
def test_maybe_auto_reopen_only_from_remediated_or_false_positive(status, should_reopen):
    finding = _make_finding(status)
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        reopened = maybe_auto_reopen(session, finding, reason="re-observed")
        session.commit()

        assert reopened is should_reopen
        refreshed = session.get(Finding, finding.id)
        if should_reopen:
            assert refreshed.status == FindingStatus.REOPENED
            history = session.execute(
                select(FindingStatusHistory).where(FindingStatusHistory.finding_id == finding.id)
            ).scalar_one()
            assert history.triggered_by == "automatic"
        else:
            assert refreshed.status == status
    finally:
        session.close()


def test_accepted_risk_never_auto_reopens_even_across_multiple_reobservations():
    finding = _make_finding(FindingStatus.ACCEPTED_RISK)
    session = get_sync_session()
    try:
        finding = session.get(Finding, finding.id)
        for _ in range(3):
            maybe_auto_reopen(session, finding, reason="re-observed again")
        session.commit()

        refreshed = session.get(Finding, finding.id)
        assert refreshed.status == FindingStatus.ACCEPTED_RISK
    finally:
        session.close()
