"""Regression tests untuk bug hasil audit (backend + frontend)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.exceptions import BusinessRuleViolation
from apps.masterdata.models import Department, Item
from apps.orders.models import POStatus
from apps.requisitions.models import PRStatus, PurchaseRequest
from apps.sourcing.models import QuotationStatus, RFQStatus
from services import (
    order_service,
    receiving_service,
    requisition_service,
    sourcing_service,
    state_machine,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def req(make_user):
    return make_user("bf_req", Role.REQUESTER)


@pytest.fixture
def other_req(make_user):
    return make_user("bf_req2", Role.REQUESTER)


@pytest.fixture
def dh(make_user):
    return make_user("bf_dh", Role.DEPT_HEAD)


@pytest.fixture
def off(make_user):
    return make_user("bf_off", Role.OFFICER)


@pytest.fixture
def mgr(make_user):
    return make_user("bf_mgr", Role.MANAGER)


@pytest.fixture
def wh(make_user):
    return make_user("bf_wh", Role.WAREHOUSE)


def _new_pr(requester, dept, item, qty="4"):
    return requisition_service.create_pr(
        requester=requester,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=14),
        reason="Regression test",
        items=[{"item": item, "qty": Decimal(qty)}],
    )


def _approved_pr(requester, dept_head, dept, item):
    pr = _new_pr(requester, dept, item)
    requisition_service.submit_pr(pr, requester)
    requisition_service.approve_pr(pr, dept_head)
    pr.refresh_from_db()
    return pr


def _rfq_sent(pr, officer, vendor):
    rfq = sourcing_service.create_rfq(
        pr,
        officer,
        datetime.date.today() + datetime.timedelta(days=7),
        [vendor.pk],
    )
    sourcing_service.send_rfq(rfq, officer)
    rfq.refresh_from_db()
    return rfq


def _quotation_submitted(rfq, pr, officer, price="1000"):
    rfq_vendor = rfq.rfq_vendors.select_related("vendor").order_by("pk").first()
    quotation = sourcing_service.submit_quotation(
        rfq_vendor,
        officer,
        lead_time_days=3,
        valid_until=None,
        terms="Net 30",
        items=[{"pr_item": pr.items.get(), "unit_price": Decimal(price)}],
    )
    return rfq_vendor, quotation


def _po_sent(pr, officer, manager, rfq, quotation):
    sourcing_service.select_quotation(quotation, officer, "Harga terbaik")
    sourcing_service.approve_vendor_selection(quotation, manager)
    po = order_service.create_po(quotation, officer)
    order_service.approve_po(po, manager)
    order_service.send_po(po, officer)
    po.refresh_from_db()
    return po


# ──────────────────────────────────────────────────────────────────────────────
# Service rules
# ──────────────────────────────────────────────────────────────────────────────


def test_dept_head_other_department_cannot_approve(req, dept, item, make_user):
    other_dept = Department.objects.create(code="HR", name="Human Resources")
    other_dh = make_user("bf_dh_other", Role.DEPT_HEAD)
    other_dh.department = other_dept
    other_dh.save(update_fields=["department"])

    pr = _new_pr(req, dept, item)
    requisition_service.submit_pr(pr, req)

    with pytest.raises(BusinessRuleViolation, match="departemen"):
        requisition_service.approve_pr(pr, other_dh)


def test_requester_cannot_cancel_someone_elses_pr(req, other_req, dept, item):
    pr = _new_pr(req, dept, item)
    with pytest.raises(BusinessRuleViolation, match="pembuat"):
        requisition_service.cancel_pr(pr, other_req)


def test_duplicate_pr_items_rejected(req, dept, item):
    with pytest.raises(BusinessRuleViolation, match="duplikat"):
        requisition_service.create_pr(
            requester=req,
            department=dept,
            needed_date=datetime.date.today(),
            reason="Duplicate",
            items=[
                {"item": item, "qty": Decimal("1")},
                {"item": item, "qty": Decimal("2")},
            ],
        )


def test_quotation_item_must_belong_to_rfq_pr(req, dh, off, dept, item, vendor):
    other_item = Item.objects.create(code="MOU-01", name="Mouse", uom="unit")
    pr = _approved_pr(req, dh, dept, item)
    rfq = _rfq_sent(pr, off, vendor)
    rfq_vendor = rfq.rfq_vendors.get()

    with pytest.raises(BusinessRuleViolation, match="bukan milik PR"):
        sourcing_service.submit_quotation(
            rfq_vendor,
            off,
            lead_time_days=3,
            valid_until=None,
            terms="",
            items=[{"pr_item": other_item, "unit_price": Decimal("10")}],
        )


def test_rejected_quotation_can_be_revised_and_resubmitted(req, dh, off, mgr, dept, item, vendor):
    pr = _approved_pr(req, dh, dept, item)
    rfq = _rfq_sent(pr, off, vendor)
    rfq_vendor, quotation = _quotation_submitted(rfq, pr, off)

    sourcing_service.select_quotation(quotation, off, "Harga terbaik")
    sourcing_service.reject_vendor_selection(quotation, mgr, "Harga masih tinggi")
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.REJECTED

    sourcing_service.submit_quotation(
        rfq_vendor,
        off,
        lead_time_days=2,
        valid_until=None,
        terms="Net 15",
        items=[{"pr_item": pr.items.get(), "unit_price": Decimal("900")}],
    )
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SUBMITTED

    sourcing_service.select_quotation(quotation, off, "Sudah direvisi")
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.SELECTED


def test_cannot_select_second_vendor_while_pending_approval(req, dh, off, dept, item, vendor):
    from apps.masterdata.models import Vendor

    vendor2 = Vendor.objects.create(code="V-BF-2", name="Vendor Dua")
    pr = _approved_pr(req, dh, dept, item)
    rfq = sourcing_service.create_rfq(
        pr, off, datetime.date.today() + datetime.timedelta(days=7), [vendor.pk, vendor2.pk]
    )
    sourcing_service.send_rfq(rfq, off)
    _, first = _quotation_submitted(rfq, pr, off, price="1000")

    second_rv = rfq.rfq_vendors.get(vendor=vendor2)
    second = sourcing_service.submit_quotation(
        second_rv,
        off,
        lead_time_days=4,
        valid_until=None,
        terms="",
        items=[{"pr_item": pr.items.get(), "unit_price": Decimal("2000")}],
    )

    sourcing_service.select_quotation(first, off, "Pilihan pertama")
    with pytest.raises(BusinessRuleViolation, match="menunggu approval"):
        sourcing_service.select_quotation(second, off, "Pilihan kedua")


def test_create_po_requires_awarded_rfq(req, dh, off, dept, item, vendor):
    pr = _approved_pr(req, dh, dept, item)
    rfq = _rfq_sent(pr, off, vendor)
    _, quotation = _quotation_submitted(rfq, pr, off)

    sourcing_service.select_quotation(quotation, off, "Harga terbaik")
    # Paksa quotation APPROVED tanpa award RFQ untuk menguji guard RFQ.
    state_machine.transition(quotation, QuotationStatus.APPROVED, off, "uji guard")
    quotation.refresh_from_db()
    rfq.refresh_from_db()
    assert quotation.status == QuotationStatus.APPROVED
    assert rfq.status != RFQStatus.AWARDED
    with pytest.raises(BusinessRuleViolation, match="AWARDED"):
        order_service.create_po(quotation, off)


# ──────────────────────────────────────────────────────────────────────────────
# Receiving bugfixes
# ──────────────────────────────────────────────────────────────────────────────


def test_two_partial_receipts_then_complete(req, dh, off, mgr, wh, dept, item, vendor):
    pr = _approved_pr(req, dh, dept, item)
    rfq = _rfq_sent(pr, off, vendor)
    _, quotation = _quotation_submitted(rfq, pr, off)
    po = _po_sent(pr, off, mgr, rfq, quotation)
    po_item = po.items.get()

    receiving_service.create_gr(
        po=po,
        receiver=wh,
        delivery_note_no="SJ-BF-1",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("1")}],
    )
    po.refresh_from_db()
    assert po.status == POStatus.PARTIALLY_RECEIVED

    # Penerimaan sebagian kedua tidak boleh memicu transisi PARTIALLY -> PARTIALLY.
    receiving_service.create_gr(
        po=po,
        receiver=wh,
        delivery_note_no="SJ-BF-2",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("1")}],
    )
    po.refresh_from_db()
    pr.refresh_from_db()
    assert po.status == POStatus.PARTIALLY_RECEIVED
    assert pr.status == PRStatus.PARTIALLY_RECEIVED

    receiving_service.create_gr(
        po=po,
        receiver=wh,
        delivery_note_no="SJ-BF-3",
        received_date=datetime.date.today(),
        items=[{"po_item": po_item, "qty_received": Decimal("2")}],
    )
    po.refresh_from_db()
    pr.refresh_from_db()
    assert po.status == POStatus.COMPLETED
    assert pr.status == PRStatus.COMPLETED


def test_gr_rejects_duplicate_and_invalid_condition(req, dh, off, mgr, wh, dept, item, vendor):
    pr = _approved_pr(req, dh, dept, item)
    rfq = _rfq_sent(pr, off, vendor)
    _, quotation = _quotation_submitted(rfq, pr, off)
    po = _po_sent(pr, off, mgr, rfq, quotation)
    po_item = po.items.get()

    with pytest.raises(BusinessRuleViolation, match="duplikat"):
        receiving_service.create_gr(
            po=po,
            receiver=wh,
            delivery_note_no="SJ-BF-DUP",
            received_date=datetime.date.today(),
            items=[
                {"po_item": po_item, "qty_received": Decimal("1")},
                {"po_item": po_item, "qty_received": Decimal("1")},
            ],
        )

    with pytest.raises(BusinessRuleViolation, match="Kondisi"):
        receiving_service.create_gr(
            po=po,
            receiver=wh,
            delivery_note_no="SJ-BF-COND",
            received_date=datetime.date.today(),
            items=[
                {
                    "po_item": po_item,
                    "qty_received": Decimal("1"),
                    "condition": "RUSAK_PARAH",
                }
            ],
        )


# ──────────────────────────────────────────────────────────────────────────────
# Frontend/view smoke tests
# ──────────────────────────────────────────────────────────────────────────────


def _login(client, user):
    client.force_login(user)
    return client


def test_pr_create_form_renders_and_submits(client, req, dept, item):
    req.department = dept
    req.save(update_fields=["department"])
    _login(client, req)

    assert client.get(reverse("pr_create")).status_code == 200
    response = client.post(
        reverse("pr_create"),
        {
            "needed_date": (datetime.date.today() + datetime.timedelta(days=14)).isoformat(),
            "reason": "Form create regression test",
            "item_id": [str(item.pk)],
            "qty": ["2"],
            "notes": ["Catatan"],
        },
    )
    assert response.status_code == 302
    pr = PurchaseRequest.objects.get(reason="Form create regression test")
    assert pr.status == PRStatus.DRAFT
    assert pr.items.count() == 1


def test_manager_can_open_rfq_list(client, mgr):
    _login(client, mgr)
    response = client.get(reverse("rfq_list"))
    assert response.status_code == 200


def test_requester_cannot_view_other_requester_pr(client, req, other_req, dept, item):
    pr = _new_pr(other_req, dept, item)
    _login(client, req)
    response = client.get(reverse("pr_detail", args=[pr.pk]))
    assert response.status_code == 403


def test_po_print_and_gr_form_render(client, req, dh, off, mgr, wh, dept, item, vendor):
    pr = _approved_pr(req, dh, dept, item)
    rfq = _rfq_sent(pr, off, vendor)
    _, quotation = _quotation_submitted(rfq, pr, off)
    po = _po_sent(pr, off, mgr, rfq, quotation)

    _login(client, off)
    assert client.get(reverse("po_print", args=[po.pk])).status_code == 200

    _login(client, wh)
    assert client.get(reverse("gr_create", args=[po.pk])).status_code == 200
    assert client.get(reverse("gr_list")).status_code == 200


def test_quotation_form_and_compare_render(client, req, dh, off, mgr, dept, item, vendor):
    pr = _approved_pr(req, dh, dept, item)
    rfq = _rfq_sent(pr, off, vendor)
    _quotation_submitted(rfq, pr, off)

    _login(client, off)
    response = client.get(
        reverse("quotation_input", args=[rfq.pk, rfq.rfq_vendors.get().vendor_id])
    )
    assert response.status_code == 200
    assert client.get(reverse("quotation_compare", args=[rfq.pk])).status_code == 200


def test_dashboard_renders_for_each_role(client, req, dh, off, mgr, wh, dept, item):
    pr = _new_pr(req, dept, item)
    requisition_service.submit_pr(pr, req)

    for user in (req, dh, off, mgr, wh):
        _login(client, user)
        assert client.get(reverse("dashboard")).status_code == 200
