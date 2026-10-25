"""
Integration tests — skenario end-to-end (LANGKAH 5).

Skenario yang diuji:
  1. Happy path lengkap: PR → Approval → RFQ → Quotation → PO → GR (COMPLETED)
  2. PR ditolak (rejected path)
  3. Partial receipt → second receipt → COMPLETED
  4. Over-receipt via test integrasi
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from apps.accounts.models import Role
from apps.core.exceptions import BusinessRuleViolation
from apps.orders.models import POStatus
from apps.receiving.models import Condition
from apps.requisitions.models import PRStatus
from apps.sourcing.models import QuotationStatus, RFQStatus
from services import (
    order_service,
    receiving_service,
    requisition_service,
    sourcing_service,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def req(make_user):
    return make_user("int_req", Role.REQUESTER)


@pytest.fixture
def dh(make_user):
    return make_user("int_dh", Role.DEPT_HEAD)


@pytest.fixture
def off(make_user):
    return make_user("int_off", Role.OFFICER)


@pytest.fixture
def mgr(make_user):
    return make_user("int_mgr", Role.MANAGER)


@pytest.fixture
def wh(make_user):
    return make_user("int_wh", Role.WAREHOUSE)


@pytest.fixture
def vendor2(db):
    from apps.masterdata.models import Vendor

    return Vendor.objects.create(code="V-INT-002", name="PT Integrasi Dua")


# ──────────────────────────────────────────────────────────────────────────────
# Skenario 1: Happy path lengkap
# ──────────────────────────────────────────────────────────────────────────────


def test_happy_path_full_flow(req, dh, off, mgr, wh, dept, item, vendor):
    """
    PR DRAFT → SUBMITTED → APPROVED → IN_SOURCING (RFQ) →
    Quotation SELECTED → APPROVED (Manager) →
    PO PENDING_APPROVAL → APPROVED → SENT →
    GR → PO COMPLETED → PR COMPLETED.
    """
    # 1. Buat PR
    pr = requisition_service.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=30),
        reason="Happy path integration test",
        items=[{"item": item, "qty": Decimal("4")}],
    )
    assert pr.status == PRStatus.DRAFT

    # 2. Submit PR
    requisition_service.submit_pr(pr, req)
    pr.refresh_from_db()
    assert pr.status == PRStatus.SUBMITTED

    # 3. Dept Head approve
    requisition_service.approve_pr(pr, dh)
    pr.refresh_from_db()
    assert pr.status == PRStatus.APPROVED

    # 4. Officer buat RFQ → PR menjadi IN_SOURCING
    rfq = sourcing_service.create_rfq(
        pr,
        off,
        due_date=datetime.date.today() + datetime.timedelta(days=7),
        vendor_ids=[vendor.pk],
    )
    pr.refresh_from_db()
    assert pr.status == PRStatus.IN_SOURCING
    assert rfq.status == RFQStatus.DRAFT

    # 5. Kirim RFQ
    sourcing_service.send_rfq(rfq, off)
    rfq.refresh_from_db()
    assert rfq.status == RFQStatus.SENT

    # 6. Input Quotation
    rfq_vendor = rfq.rfq_vendors.first()
    pr_item = pr.items.first()
    quotation = sourcing_service.submit_quotation(
        rfq_vendor,
        off,
        lead_time_days=7,
        valid_until=None,
        terms="Net 30",
        items=[{"pr_item": pr_item, "unit_price": Decimal("5000000")}],
    )
    assert quotation.status == QuotationStatus.SUBMITTED

    # 7. Officer pilih vendor
    sourcing_service.select_quotation(quotation, off, "Satu-satunya penawaran")
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SELECTED

    # 8. Manager setujui vendor selection
    sourcing_service.approve_vendor_selection(quotation, mgr)
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.APPROVED
    rfq.refresh_from_db()
    assert rfq.status == RFQStatus.AWARDED

    # 9. Officer terbitkan PO
    po = order_service.create_po(quotation, off)
    assert po.status == POStatus.PENDING_APPROVAL
    assert po.total_amount == Decimal("20000000")  # 4 × 5_000_000

    # 10. Manager approve PO
    order_service.approve_po(po, mgr)
    po.refresh_from_db()
    assert po.status == POStatus.APPROVED

    # 11. Officer kirim PO → PR menjadi PO_ISSUED
    order_service.send_po(po, off)
    po.refresh_from_db()
    pr.refresh_from_db()
    assert po.status == POStatus.SENT
    assert pr.status == PRStatus.PO_ISSUED

    # 12. Warehouse catat GR (semua item)
    po_item = po.items.first()
    gr = receiving_service.create_gr(
        po=po,
        receiver=wh,
        delivery_note_no="SJ-INTEG-001",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("4"), "condition": Condition.OK}],
    )
    po.refresh_from_db()
    pr.refresh_from_db()
    assert po.status == POStatus.COMPLETED
    assert pr.status == PRStatus.COMPLETED
    assert gr.number.startswith("GR-")


# ──────────────────────────────────────────────────────────────────────────────
# Skenario 2: PR ditolak (rejected path)
# ──────────────────────────────────────────────────────────────────────────────


def test_pr_rejected_then_revised_and_resubmitted(req, dh, dept, item):
    """
    PR DRAFT → SUBMITTED → REJECTED → (revisi) → DRAFT → SUBMITTED → APPROVED.
    """
    pr = requisition_service.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=14),
        reason="Test rejected path",
        items=[{"item": item, "qty": Decimal("2")}],
    )
    requisition_service.submit_pr(pr, req)
    requisition_service.reject_pr(pr, dh, reason="Anggaran tidak tersedia saat ini")
    pr.refresh_from_db()
    assert pr.status == PRStatus.REJECTED

    # Revisi
    requisition_service.revise_pr(pr, req)
    pr.refresh_from_db()
    assert pr.status == PRStatus.DRAFT

    # Edit lalu ajukan ulang
    requisition_service.update_pr(pr, req, reason="Perlu segera — sudah ada anggaran darurat")
    requisition_service.submit_pr(pr, req)
    pr.refresh_from_db()
    assert pr.status == PRStatus.SUBMITTED

    # Disetujui kali kedua
    requisition_service.approve_pr(pr, dh)
    pr.refresh_from_db()
    assert pr.status == PRStatus.APPROVED


# ──────────────────────────────────────────────────────────────────────────────
# Skenario 3: Partial receipt → second receipt → COMPLETED
# ──────────────────────────────────────────────────────────────────────────────


def test_partial_receipt_then_complete(req, dh, off, mgr, wh, dept, item, vendor):
    """
    GR 1 = 6 dari 10 → PARTIALLY_RECEIVED
    GR 2 = 4 sisa → COMPLETED
    """
    pr = requisition_service.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=21),
        reason="Partial receipt test",
        items=[{"item": item, "qty": Decimal("10")}],
    )
    requisition_service.submit_pr(pr, req)
    requisition_service.approve_pr(pr, dh)

    rfq = sourcing_service.create_rfq(
        pr, off, datetime.date.today() + datetime.timedelta(days=3), [vendor.pk]
    )
    sourcing_service.send_rfq(rfq, off)
    rv = rfq.rfq_vendors.first()
    q = sourcing_service.submit_quotation(
        rv,
        off,
        lead_time_days=5,
        valid_until=None,
        terms="",
        items=[{"pr_item": pr.items.first(), "unit_price": Decimal("100000")}],
    )
    sourcing_service.select_quotation(q, off, "OK")
    sourcing_service.approve_vendor_selection(q, mgr)
    po = order_service.create_po(q, off)
    order_service.approve_po(po, mgr)
    order_service.send_po(po, off)

    po_item = po.items.first()

    # GR 1: terima 6
    receiving_service.create_gr(
        po,
        wh,
        "SJ-P-001",
        datetime.date.today(),
        [{"po_item": po_item, "qty_received": Decimal("6")}],
    )
    po.refresh_from_db()
    assert po.status == POStatus.PARTIALLY_RECEIVED

    # GR 2: terima sisa 4
    receiving_service.create_gr(
        po,
        wh,
        "SJ-P-002",
        datetime.date.today(),
        [{"po_item": po_item, "qty_received": Decimal("4")}],
    )
    po.refresh_from_db()
    pr.refresh_from_db()
    assert po.status == POStatus.COMPLETED
    assert pr.status == PRStatus.COMPLETED


# ──────────────────────────────────────────────────────────────────────────────
# Skenario 4: Over-receipt ditolak (integrasi)
# ──────────────────────────────────────────────────────────────────────────────


def test_over_receipt_integration(req, dh, off, mgr, wh, dept, item, vendor):
    """Konfirmasi BR-05 lewat skenario end-to-end."""
    pr = requisition_service.create_pr(
        requester=req,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=10),
        reason="Over receipt test",
        items=[{"item": item, "qty": Decimal("5")}],
    )
    requisition_service.submit_pr(pr, req)
    requisition_service.approve_pr(pr, dh)
    rfq = sourcing_service.create_rfq(
        pr, off, datetime.date.today() + datetime.timedelta(days=2), [vendor.pk]
    )
    sourcing_service.send_rfq(rfq, off)
    rv = rfq.rfq_vendors.first()
    q = sourcing_service.submit_quotation(
        rv,
        off,
        lead_time_days=3,
        valid_until=None,
        terms="",
        items=[{"pr_item": pr.items.first(), "unit_price": Decimal("50000")}],
    )
    sourcing_service.select_quotation(q, off, "OK")
    sourcing_service.approve_vendor_selection(q, mgr)
    po = order_service.create_po(q, off)
    order_service.approve_po(po, mgr)
    order_service.send_po(po, off)

    po_item = po.items.first()

    # Coba terima 99 — harus ditolak
    with pytest.raises(BusinessRuleViolation, match="[Mm]elebihi|sisa|BR-05"):
        receiving_service.create_gr(
            po,
            wh,
            "SJ-OVER-INT",
            datetime.date.today(),
            [{"po_item": po_item, "qty_received": Decimal("99")}],
        )

    # PO masih SENT (tidak berubah)
    po.refresh_from_db()
    assert po.status == POStatus.SENT
