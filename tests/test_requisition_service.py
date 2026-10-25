"""
Tests: requisition service.

FR/BR tercakup:
  FR-020  buat PR dengan nomor otomatis, ≥ 1 item, qty > 0
  FR-021  edit/hapus PR DRAFT; hanya pembuat
  FR-022  submit → SUBMITTED + Approval PENDING
  FR-023  Dept Head approve/reject (alasan wajib); approver ≠ requester
  FR-024  REJECTED → DRAFT (revisi)
  FR-025  Officer tandai IN_SOURCING (dipanggil dari sourcing_service)
  BR-01   segregation of duties
  BR-06   dokumen final tidak dapat diubah
"""

import datetime

import pytest

from apps.accounts.models import Role
from apps.approvals.models import ApprovalStatus
from apps.core.exceptions import BusinessRuleViolation, InvalidTransition
from apps.requisitions.models import PRStatus
from services import requisition_service as svc

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures lokal
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def requester(make_user):
    return make_user("req_svc", Role.REQUESTER)


@pytest.fixture
def dept_head(make_user):
    return make_user("dhead_svc", Role.DEPT_HEAD)


@pytest.fixture
def officer(make_user):
    return make_user("off_svc", Role.OFFICER)


@pytest.fixture
def new_pr(requester, dept, item):
    """PR DRAFT baru lewat service."""
    return svc.create_pr(
        requester=requester,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=14),
        reason="Test PR",
        items=[{"item": item, "qty": 3, "notes": ""}],
    )


# ──────────────────────────────────────────────────────────────────────────────
# FR-020: buat PR
# ──────────────────────────────────────────────────────────────────────────────


def test_create_pr_generates_number(requester, dept, item):
    pr = svc.create_pr(
        requester=requester,
        department=dept,
        needed_date=datetime.date.today(),
        reason="Test",
        items=[{"item": item, "qty": 2}],
    )
    assert pr.number.startswith("PR-")
    assert pr.status == PRStatus.DRAFT


def test_create_pr_requires_at_least_one_item(requester, dept):
    with pytest.raises(BusinessRuleViolation, match="minimal 1 item"):
        svc.create_pr(
            requester=requester,
            department=dept,
            needed_date=datetime.date.today(),
            reason="Test",
            items=[],
        )


def test_create_pr_qty_must_be_positive(requester, dept, item):
    with pytest.raises(BusinessRuleViolation, match="Qty.*harus > 0"):
        svc.create_pr(
            requester=requester,
            department=dept,
            needed_date=datetime.date.today(),
            reason="Test",
            items=[{"item": item, "qty": 0}],
        )


# ──────────────────────────────────────────────────────────────────────────────
# FR-021: edit dan hapus PR DRAFT
# ──────────────────────────────────────────────────────────────────────────────


def test_update_pr_draft(new_pr, requester):
    svc.update_pr(new_pr, requester, reason="Alasan baru")
    new_pr.refresh_from_db()
    assert new_pr.reason == "Alasan baru"


def test_update_pr_non_draft_rejected(new_pr, requester, dept_head):
    svc.submit_pr(new_pr, requester)
    with pytest.raises(BusinessRuleViolation, match="DRAFT"):
        svc.update_pr(new_pr, requester, reason="x")


def test_only_creator_can_update_pr(new_pr, make_user):
    other = make_user("other_req", Role.REQUESTER)
    with pytest.raises(BusinessRuleViolation, match="pembuat"):
        svc.update_pr(new_pr, other, reason="hack")


def test_delete_pr_draft(new_pr, requester):
    from apps.requisitions.models import PurchaseRequest

    pr_id = new_pr.pk
    svc.delete_pr(new_pr, requester)
    assert not PurchaseRequest.objects.filter(pk=pr_id).exists()


def test_delete_pr_non_draft_rejected(new_pr, requester):
    svc.submit_pr(new_pr, requester)
    with pytest.raises(BusinessRuleViolation, match="DRAFT"):
        svc.delete_pr(new_pr, requester)


# ──────────────────────────────────────────────────────────────────────────────
# FR-022: submit PR
# ──────────────────────────────────────────────────────────────────────────────


def test_submit_pr_creates_approval(new_pr, requester):
    approval = svc.submit_pr(new_pr, requester)
    new_pr.refresh_from_db()
    assert new_pr.status == PRStatus.SUBMITTED
    assert approval.status == ApprovalStatus.PENDING
    assert approval.required_role == Role.DEPT_HEAD


def test_submit_pr_only_by_creator(new_pr, make_user):
    other = make_user("other2", Role.REQUESTER)
    with pytest.raises(BusinessRuleViolation, match="pembuat"):
        svc.submit_pr(new_pr, other)


# ──────────────────────────────────────────────────────────────────────────────
# FR-023 + BR-01: approve/reject
# ──────────────────────────────────────────────────────────────────────────────


def test_approve_pr_happy_path(new_pr, requester, dept_head):
    svc.submit_pr(new_pr, requester)
    svc.approve_pr(new_pr, dept_head)
    new_pr.refresh_from_db()
    assert new_pr.status == PRStatus.APPROVED


def test_reject_pr_requires_reason(new_pr, requester, dept_head):
    svc.submit_pr(new_pr, requester)
    with pytest.raises(BusinessRuleViolation, match="[Aa]lasan"):
        svc.reject_pr(new_pr, dept_head, reason="")


def test_reject_pr_happy_path(new_pr, requester, dept_head):
    svc.submit_pr(new_pr, requester)
    svc.reject_pr(new_pr, dept_head, reason="Anggaran tidak cukup")
    new_pr.refresh_from_db()
    assert new_pr.status == PRStatus.REJECTED


def test_requester_cannot_self_approve(new_pr, requester, make_user):
    """BR-01: requester ≠ approver."""
    # Requester juga berperan sebagai dept head (role diubah sementara)
    requester.role = Role.DEPT_HEAD
    requester.save()
    svc.submit_pr(new_pr, requester)
    with pytest.raises(BusinessRuleViolation, match="[Ss]egregation|pembuat|sendiri"):
        svc.approve_pr(new_pr, requester)


def test_wrong_role_cannot_approve(new_pr, requester, make_user):
    svc.submit_pr(new_pr, requester)
    wrong_role_user = make_user("wrong_role", Role.OFFICER)
    with pytest.raises(BusinessRuleViolation, match="role"):
        svc.approve_pr(new_pr, wrong_role_user)


# ──────────────────────────────────────────────────────────────────────────────
# FR-024: revisi PR
# ──────────────────────────────────────────────────────────────────────────────


def test_revise_rejected_pr(new_pr, requester, dept_head):
    svc.submit_pr(new_pr, requester)
    svc.reject_pr(new_pr, dept_head, reason="Budget habis")
    svc.revise_pr(new_pr, requester)
    new_pr.refresh_from_db()
    assert new_pr.status == PRStatus.DRAFT


def test_only_requester_can_revise(new_pr, requester, dept_head, make_user):
    svc.submit_pr(new_pr, requester)
    svc.reject_pr(new_pr, dept_head, reason="x")
    other = make_user("other3", Role.REQUESTER)
    with pytest.raises(BusinessRuleViolation, match="pembuat"):
        svc.revise_pr(new_pr, other)


# ──────────────────────────────────────────────────────────────────────────────
# BR-06: dokumen final tidak dapat diubah
# ──────────────────────────────────────────────────────────────────────────────


def test_completed_pr_cannot_be_cancelled(new_pr, requester, dept_head, officer, item, vendor):
    """Status COMPLETED tidak boleh ditransisi ke CANCELLED."""
    svc.submit_pr(new_pr, requester)
    svc.approve_pr(new_pr, dept_head)
    # Paksa ke COMPLETED via state machine (tanpa melalui sourcing)
    from services.state_machine import transition as sm_transition

    sm_transition(new_pr, "IN_SOURCING", officer)
    sm_transition(new_pr, "PO_ISSUED", officer)
    sm_transition(new_pr, "COMPLETED", officer)

    with pytest.raises(InvalidTransition):
        svc.cancel_pr(new_pr, requester)
