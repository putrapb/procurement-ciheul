"""
Tests: approval rules (gate L023 — test_requester_cannot_self_approve).

Digunakan oleh gate L023 di law.bend:
  pytest tests/test_approval_rules.py::test_requester_cannot_self_approve -q
"""

import datetime

import pytest

from apps.accounts.models import Role
from apps.core.exceptions import BusinessRuleViolation
from apps.requisitions.models import PRStatus
from services import requisition_service as svc


@pytest.fixture
def requester_as_dept_head(make_user, dept, item):
    """User yang berperan sebagai requester sekaligus dept head (untuk uji BR-01)."""
    u = make_user("dual_role", Role.DEPT_HEAD)
    return u


@pytest.fixture
def pr_for_dual(make_user, dept, item):
    req = make_user("req_dual", Role.REQUESTER)
    pr = svc.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=7),
        reason="Test BR-01",
        items=[{"item": item, "qty": 1}],
    )
    return pr, req


def test_requester_cannot_self_approve(pr_for_dual):
    """
    BR-01: Pembuat PR tidak boleh meng-approve PR yang sama.
    Gate L023 memanggil test ini secara langsung.
    """
    pr, requester = pr_for_dual
    # Ubah role requester ke DEPT_HEAD agar lolos cek role
    requester.role = Role.DEPT_HEAD
    requester.save()

    svc.submit_pr(pr, requester)
    with pytest.raises(BusinessRuleViolation, match="[Ss]egregation|pembuat|sendiri"):
        svc.approve_pr(pr, requester)


def test_different_user_can_approve(make_user, dept, item):
    """User berbeda dengan role DEPT_HEAD dapat menyetujui PR."""
    req = make_user("req_ok", Role.REQUESTER)
    dhead = make_user("dh_ok", Role.DEPT_HEAD)

    pr = svc.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=7),
        reason="Test",
        items=[{"item": item, "qty": 2}],
    )
    svc.submit_pr(pr, req)
    svc.approve_pr(pr, dhead)
    pr.refresh_from_db()
    assert pr.status == PRStatus.APPROVED
