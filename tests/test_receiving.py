"""
Tests: receiving service (gate L024 — test_over_receipt_rejected).

FR/BR tercakup:
  FR-050  Buat GR untuk PO SENT/PARTIALLY_RECEIVED
  FR-051  qty diterima tidak boleh melebihi sisa qty PO
  FR-052  Jika semua item terpenuhi → PO + PR COMPLETED; sebagian → PARTIALLY_RECEIVED
  BR-05  GR tidak boleh melebihi sisa qty PO
"""

import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.core.exceptions import BusinessRuleViolation
from apps.orders.models import POStatus
from apps.receiving.models import Condition
from apps.requisitions.models import PRStatus
from services import order_service, receiving_service, requisition_service, sourcing_service

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def officer(make_user):
    return make_user("off_rcv", Role.OFFICER)


@pytest.fixture
def manager(make_user):
    return make_user("mgr_rcv", Role.MANAGER)


@pytest.fixture
def dept_head(make_user):
    return make_user("dh_rcv", Role.DEPT_HEAD)


@pytest.fixture
def warehouse(make_user):
    return make_user("wh_rcv", Role.WAREHOUSE)


@pytest.fixture
def sent_po(make_user, dept, item, vendor, officer, manager, dept_head):
    """PO yang sudah dikirim ke vendor — siap menerima GR."""
    req = make_user("req_rcv", Role.REQUESTER)
    pr = requisition_service.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=30),
        reason="Test receiving",
        items=[{"item": item, "qty": Decimal("10")}],
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
        lead_time_days=5,
        valid_until=None,
        terms="",
        items=[{"pr_item": pr_item, "unit_price": Decimal("1000000")}],
    )
    sourcing_service.select_quotation(quotation, officer, "OK")
    sourcing_service.approve_vendor_selection(quotation, manager)

    po = order_service.create_po(quotation, officer)
    order_service.approve_po(po, manager)
    order_service.send_po(po, officer)
    return po


# ──────────────────────────────────────────────────────────────────────────────
# FR-050: buat GR
# ──────────────────────────────────────────────────────────────────────────────


def test_create_gr_happy_path(sent_po, warehouse):
    po_item = sent_po.items.first()
    gr = receiving_service.create_gr(
        po=sent_po,
        receiver=warehouse,
        delivery_note_no="SJ-001",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("5"), "condition": Condition.OK}],
    )
    assert gr.number.startswith("GR-")
    sent_po.refresh_from_db()
    assert sent_po.status == POStatus.PARTIALLY_RECEIVED


def test_gr_requires_warehouse_role(sent_po, manager):
    po_item = sent_po.items.first()
    with pytest.raises(BusinessRuleViolation, match="role"):
        receiving_service.create_gr(
            po=sent_po,
            receiver=manager,
            delivery_note_no="SJ-X",
            received_date=datetime.date.today(),
            items=[{"po_item": po_item, "qty_received": Decimal("1")}],
        )


def test_gr_only_for_sent_po(sent_po, warehouse, officer):
    """GR tidak bisa dibuat untuk PO yang belum SENT."""
    # Tidak praktis tanpa fixture baru, test negatif via status check
    # Paksa status melalui DB langsung (hanya untuk test ini) — BUKAN production code
    sent_po.status = POStatus.APPROVED
    sent_po.save(update_fields=["status"])
    po_item = sent_po.items.first()
    with pytest.raises(BusinessRuleViolation, match="SENT|PARTIALLY_RECEIVED"):
        receiving_service.create_gr(
            po=sent_po,
            receiver=warehouse,
            delivery_note_no="SJ-Y",
            received_date=datetime.date.today(),
            items=[{"po_item": po_item, "qty_received": Decimal("1")}],
        )


# ──────────────────────────────────────────────────────────────────────────────
# FR-051 + BR-05: over-receipt ditolak
# ──────────────────────────────────────────────────────────────────────────────


def test_over_receipt_rejected(sent_po, warehouse):
    """Gate L024: qty diterima melebihi sisa PO → BusinessRuleViolation."""
    po_item = sent_po.items.first()
    with pytest.raises(BusinessRuleViolation, match="[Mm]elebihi|sisa|BR-05"):
        receiving_service.create_gr(
            po=sent_po,
            receiver=warehouse,
            delivery_note_no="SJ-OVER",
            received_date=datetime.date.today(),
            items=[{"po_item": po_item, "qty_received": Decimal("999")}],
        )


def test_over_receipt_after_partial(sent_po, warehouse):
    """GR kedua tidak boleh melebihi sisa setelah GR pertama."""
    po_item = sent_po.items.first()
    # GR pertama: terima 7 dari 10
    receiving_service.create_gr(
        po=sent_po,
        receiver=warehouse,
        delivery_note_no="SJ-002",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("7")}],
    )
    sent_po.refresh_from_db()
    assert sent_po.status == POStatus.PARTIALLY_RECEIVED

    # GR kedua: coba terima 5, tapi sisa hanya 3
    with pytest.raises(BusinessRuleViolation, match="[Mm]elebihi|sisa|BR-05"):
        receiving_service.create_gr(
            po=sent_po,
            receiver=warehouse,
            delivery_note_no="SJ-003",
            received_date=datetime.date.today(),
            items=[{"po_item": po_item, "qty_received": Decimal("5")}],
        )


# ──────────────────────────────────────────────────────────────────────────────
# FR-052: status PO dan PR setelah GR
# ──────────────────────────────────────────────────────────────────────────────


def test_full_receipt_completes_po_and_pr(sent_po, warehouse):
    """Terima semua item → PO COMPLETED + PR COMPLETED."""
    po_item = sent_po.items.first()
    pr = sent_po.quotation.rfq_vendor.rfq.pr

    receiving_service.create_gr(
        po=sent_po,
        receiver=warehouse,
        delivery_note_no="SJ-FULL",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("10")}],
    )
    sent_po.refresh_from_db()
    pr.refresh_from_db()
    assert sent_po.status == POStatus.COMPLETED
    assert pr.status == PRStatus.COMPLETED


def test_partial_receipt_marks_partially_received(sent_po, warehouse):
    """Terima sebagian → PO PARTIALLY_RECEIVED, PR tetap dalam proses."""
    po_item = sent_po.items.first()
    receiving_service.create_gr(
        po=sent_po,
        receiver=warehouse,
        delivery_note_no="SJ-PART",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("3")}],
    )
    sent_po.refresh_from_db()
    assert sent_po.status == POStatus.PARTIALLY_RECEIVED
