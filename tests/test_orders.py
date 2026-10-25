"""
Tests: order service (gate L025 — test_po_immutable_after_approved).

FR/BR tercakup:
  FR-040  Buat PO dari Quotation APPROVED
  FR-041  Manager approve/reject PO
  FR-042  Officer kirim PO APPROVED → SENT
  FR-043  Officer revisi PO REJECTED
  BR-03  Total PO = sum(qty × unit_price)
  BR-04  Harga dan qty PO tidak dapat diubah setelah APPROVED
"""

import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.core.exceptions import BusinessRuleViolation
from apps.orders.models import POStatus
from services import order_service as svc
from services import requisition_service, sourcing_service

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures: bangun alur hingga Quotation APPROVED
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def officer(make_user):
    return make_user("off_ord", Role.OFFICER)


@pytest.fixture
def manager(make_user):
    return make_user("mgr_ord", Role.MANAGER)


@pytest.fixture
def dept_head(make_user):
    return make_user("dh_ord", Role.DEPT_HEAD)


@pytest.fixture
def approved_quotation(make_user, dept, item, vendor, officer, manager, dept_head):
    """Quotation yang sudah disetujui Manager — siap untuk di-PO-kan."""
    req = make_user("req_ord", Role.REQUESTER)
    pr = requisition_service.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=30),
        reason="Butuh laptop",
        items=[{"item": item, "qty": Decimal("5")}],
    )
    requisition_service.submit_pr(pr, req)
    requisition_service.approve_pr(pr, dept_head)

    rfq = sourcing_service.create_rfq(
        pr, officer, datetime.date.today() + datetime.timedelta(days=7), [vendor.pk]
    )
    sourcing_service.send_rfq(rfq, officer)

    rfq_vendor = rfq.rfq_vendors.first()
    pr_item = pr.items.first()
    quotation = sourcing_service.submit_quotation(
        rfq_vendor,
        officer,
        lead_time_days=7,
        valid_until=datetime.date.today() + datetime.timedelta(days=30),
        terms="Net 30",
        items=[{"pr_item": pr_item, "unit_price": Decimal("12000000")}],
    )
    sourcing_service.select_quotation(quotation, officer, "Harga terbaik")
    sourcing_service.approve_vendor_selection(quotation, manager)
    return quotation


# ──────────────────────────────────────────────────────────────────────────────
# FR-040 + BR-03: buat PO
# ──────────────────────────────────────────────────────────────────────────────


def test_create_po_happy_path(approved_quotation, officer):
    po = svc.create_po(approved_quotation, officer)
    assert po.status == POStatus.PENDING_APPROVAL
    assert po.total_amount == Decimal("60000000")  # 5 × 12_000_000
    assert po.items.count() == 1


def test_create_po_only_from_approved_quotation(approved_quotation, officer, manager):
    """Tidak bisa buat PO dua kali dari quotation yang sama."""
    svc.create_po(approved_quotation, officer)
    with pytest.raises(BusinessRuleViolation, match="sudah ada"):
        svc.create_po(approved_quotation, officer)


def test_create_po_requires_officer_role(approved_quotation, manager):
    with pytest.raises(BusinessRuleViolation, match="role"):
        svc.create_po(approved_quotation, manager)


# ──────────────────────────────────────────────────────────────────────────────
# FR-041: approve/reject PO
# ──────────────────────────────────────────────────────────────────────────────


def test_approve_po_happy_path(approved_quotation, officer, manager):
    po = svc.create_po(approved_quotation, officer)
    svc.approve_po(po, manager)
    po.refresh_from_db()
    assert po.status == POStatus.APPROVED


def test_reject_po_requires_reason(approved_quotation, officer, manager):
    po = svc.create_po(approved_quotation, officer)
    with pytest.raises(BusinessRuleViolation, match="[Aa]lasan"):
        svc.reject_po(po, manager, reason="")


def test_reject_po_happy_path(approved_quotation, officer, manager):
    po = svc.create_po(approved_quotation, officer)
    svc.reject_po(po, manager, reason="Anggaran tidak tersedia")
    po.refresh_from_db()
    assert po.status == POStatus.REJECTED


# ──────────────────────────────────────────────────────────────────────────────
# FR-042: kirim PO
# ──────────────────────────────────────────────────────────────────────────────


def test_send_po_happy_path(approved_quotation, officer, manager):
    po = svc.create_po(approved_quotation, officer)
    svc.approve_po(po, manager)
    svc.send_po(po, officer)
    po.refresh_from_db()
    assert po.status == POStatus.SENT


def test_send_po_from_non_approved_rejected(approved_quotation, officer, manager):
    po = svc.create_po(approved_quotation, officer)
    # Status masih PENDING_APPROVAL, belum APPROVED
    with pytest.raises(BusinessRuleViolation, match="APPROVED"):
        svc.send_po(po, officer)


# ──────────────────────────────────────────────────────────────────────────────
# FR-043 + BR-04: PO immutable setelah APPROVED
# ──────────────────────────────────────────────────────────────────────────────


def test_po_immutable_after_approved(approved_quotation, officer, manager):
    """
    BR-04 / Gate L025: Harga dan qty PO tidak boleh diubah setelah APPROVED.
    """
    po = svc.create_po(approved_quotation, officer)
    svc.approve_po(po, manager)
    # Coba ubah — harus gagal
    with pytest.raises(BusinessRuleViolation, match="[Bb]rubah|tidak dapat diubah|APPROVED"):
        svc.check_po_immutable(po)


def test_po_can_be_edited_when_pending(approved_quotation, officer):
    """PO masih PENDING_APPROVAL → check_po_immutable tidak raise."""
    po = svc.create_po(approved_quotation, officer)
    # Tidak raise = OK
    svc.check_po_immutable(po)


def test_resubmit_rejected_po(approved_quotation, officer, manager):
    po = svc.create_po(approved_quotation, officer)
    svc.reject_po(po, manager, reason="Perlu revisi harga")
    svc.resubmit_po(po, officer, "Harga sudah dikoreksi")
    po.refresh_from_db()
    assert po.status == POStatus.PENDING_APPROVAL
