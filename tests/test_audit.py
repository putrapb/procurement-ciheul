import pytest

from apps.audit.models import AuditLog
from apps.core.exceptions import InvalidTransition
from services.state_machine import transition


def test_every_transition_writes_audit(pr):
    transition(pr, "SUBMITTED", pr.requester, "ajukan")
    log = AuditLog.objects.get()
    assert (log.from_status, log.to_status, log.user, log.note) == (
        "DRAFT",
        "SUBMITTED",
        pr.requester,
        "ajukan",
    )
    assert log.target == pr


def test_failed_transition_writes_no_audit(pr):
    with pytest.raises(InvalidTransition):
        transition(pr, "COMPLETED", pr.requester)
    assert AuditLog.objects.count() == 0


def test_audit_log_append_only(pr):
    transition(pr, "SUBMITTED", pr.requester)
    log = AuditLog.objects.get()
    log.note = "diubah"
    with pytest.raises(TypeError):
        log.save()
    with pytest.raises(TypeError):
        log.delete()
    with pytest.raises(TypeError):
        AuditLog.objects.all().update(note="x")
    with pytest.raises(TypeError):
        AuditLog.objects.all().delete()
