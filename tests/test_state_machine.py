import pytest

from apps.core.exceptions import InvalidTransition
from services.state_machine import allowed_targets, transition


def test_valid_transition_updates_status(pr):
    transition(pr, "SUBMITTED", pr.requester)
    pr.refresh_from_db()
    assert pr.status == "SUBMITTED"


def test_invalid_transition_rejected(pr):
    with pytest.raises(InvalidTransition):
        transition(pr, "COMPLETED", pr.requester)
    pr.refresh_from_db()
    assert pr.status == "DRAFT"


def test_rejected_pr_can_return_to_draft(pr):
    transition(pr, "SUBMITTED", pr.requester)
    transition(pr, "REJECTED", pr.requester, "kurang detail")
    transition(pr, "DRAFT", pr.requester)
    assert pr.status == "DRAFT"


def test_final_state_has_no_exit(pr):
    transition(pr, "CANCELLED", pr.requester)
    assert allowed_targets(pr) == set()
    with pytest.raises(InvalidTransition):
        transition(pr, "DRAFT", pr.requester)
