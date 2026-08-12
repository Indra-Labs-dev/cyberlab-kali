"""Phase 16 -- Finding lifecycle state machine. Deliberately a plain Python
dict of valid transitions, not a workflow engine: the spec is small and
fixed, and a generic engine would be exactly the kind of premature
abstraction this phase is instructed to avoid.

    NEW -> CONFIRMED
    CONFIRMED -> IN_REVIEW
    IN_REVIEW -> ACCEPTED_RISK | FALSE_POSITIVE | REMEDIATED
    ACCEPTED_RISK -> REOPENED
    FALSE_POSITIVE -> REOPENED
    REMEDIATED -> REOPENED
    REOPENED -> CONFIRMED | IN_REVIEW   (resume the normal review flow)

Every transition, manual or automatic, is appended to
`finding_status_history` (app/models/finding_relation.py) -- append-only,
never edited or deleted.
"""

from sqlalchemy.orm import Session

from app.models.finding import Finding, FindingStatus
from app.models.finding_relation import FindingStatusHistory

VALID_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.NEW: {FindingStatus.CONFIRMED},
    FindingStatus.CONFIRMED: {FindingStatus.IN_REVIEW},
    FindingStatus.IN_REVIEW: {
        FindingStatus.ACCEPTED_RISK,
        FindingStatus.FALSE_POSITIVE,
        FindingStatus.REMEDIATED,
    },
    FindingStatus.ACCEPTED_RISK: {FindingStatus.REOPENED},
    FindingStatus.FALSE_POSITIVE: {FindingStatus.REOPENED},
    FindingStatus.REMEDIATED: {FindingStatus.REOPENED},
    FindingStatus.REOPENED: {FindingStatus.CONFIRMED, FindingStatus.IN_REVIEW},
}

# Statuses a *re-observation* (the same signature seen again by a job) may
# automatically reopen. ACCEPTED_RISK is deliberately excluded -- a human
# consciously decided to tolerate this finding; re-detecting the exact same
# thing must not silently override that decision (spec section 11/3).
AUTO_REOPEN_FROM = {FindingStatus.REMEDIATED, FindingStatus.FALSE_POSITIVE}


class InvalidTransitionError(ValueError):
    pass


def is_valid_transition(old_status: FindingStatus, new_status: FindingStatus) -> bool:
    return new_status in VALID_TRANSITIONS.get(old_status, set())


def transition_status(
    session: Session,
    finding: Finding,
    new_status: FindingStatus,
    *,
    reason: str | None,
    triggered_by: str,
) -> FindingStatusHistory:
    """Applies a transition and records it. Raises InvalidTransitionError
    without changing anything if the transition isn't allowed -- callers
    (the API route, or the automatic reopen check in
    app/findings/service.py) must not catch this silently.
    """
    old_status = finding.status
    if not is_valid_transition(old_status, new_status):
        raise InvalidTransitionError(
            f"cannot transition finding {finding.id} from {old_status.value} to {new_status.value}"
        )

    finding.status = new_status
    history = FindingStatusHistory(
        finding_id=finding.id,
        old_status=old_status,
        new_status=new_status,
        reason=reason,
        triggered_by=triggered_by,
    )
    session.add(history)
    return history


def maybe_auto_reopen(session: Session, finding: Finding, *, reason: str) -> bool:
    """Called on every re-observation (app/findings/service.py). Reopens
    only from REMEDIATED/FALSE_POSITIVE; a no-op for every other status,
    including ACCEPTED_RISK and including NEW/CONFIRMED/IN_REVIEW/REOPENED
    themselves (re-observing an already-NEW finding must never silently
    "auto-confirm" it -- spec section 3/9)."""
    if finding.status not in AUTO_REOPEN_FROM:
        return False
    transition_status(session, finding, FindingStatus.REOPENED, reason=reason, triggered_by="automatic")
    return True
