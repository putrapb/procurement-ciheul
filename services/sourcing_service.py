"""
Sourcing service — logika bisnis RFQ dan Quotation (F-06, F-07, F-08).

FR yang tercakup:
  FR-030  Officer buat RFQ dari PR APPROVED, ≥ 1 vendor, tentukan batas waktu
  FR-031  RFQ yang dikirim berstatus SENT
  FR-032  Officer input Quotation per vendor (harga, lead time, dll.)
  FR-033  Perbandingan penawaran (helper method — view mengakses data)
  FR-034  Officer pilih satu Quotation (SELECTED); justifikasi wajib jika bukan termurah
  FR-035  Pemilihan vendor memerlukan approval Procurement Manager

BR yang tercakup:
  BR-02  Quotation hanya dapat dipilih dari RFQ milik PR terkait
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.accounts.models import Role, User
from apps.approvals.models import Approval
from apps.core.exceptions import BusinessRuleViolation
from apps.masterdata.models import Vendor
from apps.requisitions.models import PRStatus
from apps.sourcing.models import (
    RFQ,
    Quotation,
    QuotationItem,
    QuotationStatus,
    RFQStatus,
    RFQVendor,
)
from services import approval_service
from services.numbering import next_number
from services.state_machine import transition


def _check_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise BusinessRuleViolation(
            f"Aksi ini memerlukan role {'/'.join(roles)}, bukan {user.role}."
        )


def _validate_quotation_items(items: list[dict[str, Any]], rfq: RFQ) -> None:
    if not items:
        raise BusinessRuleViolation("Quotation harus memiliki minimal 1 item harga.")
    valid_pr_item_ids = set(rfq.pr.items.values_list("pk", flat=True))
    seen: set[int] = set()
    for entry in items:
        pr_item = entry.get("pr_item")
        if pr_item is None or pr_item.pk not in valid_pr_item_ids:
            raise BusinessRuleViolation("Item penawaran bukan milik PR pada RFQ ini.")
        if pr_item.pk in seen:
            raise BusinessRuleViolation(f"Item {pr_item.item.code} duplikat dalam penawaran.")
        seen.add(pr_item.pk)
        try:
            unit_price = Decimal(str(entry.get("unit_price")))
        except (ArithmeticError, TypeError, ValueError):
            raise BusinessRuleViolation(f"Harga item {pr_item.item.code} tidak valid.") from None
        if unit_price < 0:
            raise BusinessRuleViolation("Harga satuan tidak boleh negatif.")
        entry["unit_price"] = unit_price


# ──────────────────────────────────────────────────────────────────────────────
# RFQ
# ──────────────────────────────────────────────────────────────────────────────


def create_rfq(
    pr,
    officer: User,
    due_date: datetime.date,
    vendor_ids: list[int],
) -> RFQ:
    """
    Buat RFQ dari PR APPROVED. FR-030.
    Juga menandai PR → IN_SOURCING (FR-025).
    """
    _check_role(officer, Role.OFFICER)
    if pr.status != PRStatus.APPROVED:
        raise BusinessRuleViolation("RFQ hanya dapat dibuat dari PR berstatus APPROVED.")
    if not vendor_ids:
        raise BusinessRuleViolation("RFQ harus menyertakan minimal 1 vendor.")
    unique_ids = list(dict.fromkeys(vendor_ids))
    vendors = list(Vendor.objects.filter(pk__in=unique_ids, is_active=True))
    if len(vendors) != len(unique_ids):
        raise BusinessRuleViolation("Vendor tidak ditemukan atau sudah tidak aktif.")
    if due_date is None:
        raise BusinessRuleViolation("Batas waktu RFQ wajib diisi.")

    with transaction.atomic():
        number = next_number("RFQ")
        rfq = RFQ.objects.create(
            number=number,
            pr=pr,
            due_date=due_date,
            status=RFQStatus.DRAFT,
            created_by=officer,
        )
        for vid in unique_ids:
            RFQVendor.objects.create(rfq=rfq, vendor_id=vid)

        # FR-025: tandai PR → IN_SOURCING
        from services.requisition_service import mark_in_sourcing

        mark_in_sourcing(pr, officer)
    return rfq


def send_rfq(rfq: RFQ, officer: User) -> None:
    """Tandai RFQ terkirim ke vendor (pencatatan). FR-031."""
    _check_role(officer, Role.OFFICER)
    with transaction.atomic():
        from django.utils import timezone

        rfq.rfq_vendors.all().update(sent_at=timezone.now())
        transition(rfq, RFQStatus.SENT, officer, "RFQ dikirim ke vendor")


def close_rfq(rfq: RFQ, officer: User) -> None:
    """Tutup RFQ (tidak menerima penawaran baru)."""
    _check_role(officer, Role.OFFICER)
    with transaction.atomic():
        transition(rfq, RFQStatus.CLOSED, officer, "RFQ ditutup")


# ──────────────────────────────────────────────────────────────────────────────
# Quotation
# ──────────────────────────────────────────────────────────────────────────────


def submit_quotation(
    rfq_vendor: RFQVendor,
    officer: User,
    *,
    lead_time_days: int,
    valid_until: datetime.date | None,
    terms: str,
    items: list[dict[str, Any]],
    attachment: Any = None,
) -> Quotation:
    """
    Input penawaran per vendor. FR-032.

    `items` = [{"pr_item": PRItem, "unit_price": Decimal}, ...]
    """
    _check_role(officer, Role.OFFICER)
    if lead_time_days is None or lead_time_days < 0:
        raise BusinessRuleViolation("Lead time tidak boleh negatif.")
    rfq = rfq_vendor.rfq
    if rfq.status not in (RFQStatus.SENT, RFQStatus.CLOSED):
        raise BusinessRuleViolation(
            "Penawaran hanya dapat diinput untuk RFQ berstatus SENT atau CLOSED."
        )
    _validate_quotation_items(items, rfq)

    with transaction.atomic():
        quotation = Quotation.objects.filter(rfq_vendor=rfq_vendor).first()
        if quotation is None:
            quotation = Quotation.objects.create(
                rfq_vendor=rfq_vendor,
                lead_time_days=lead_time_days,
                valid_until=valid_until,
                terms=terms,
                attachment=attachment,
                status=QuotationStatus.SUBMITTED,
            )
        else:
            if quotation.status not in (QuotationStatus.SUBMITTED, QuotationStatus.REJECTED):
                raise BusinessRuleViolation("Penawaran ini sudah tidak dapat diedit.")

            # Revisi setelah ditolak Manager harus kembali masuk antrean approval.
            if quotation.status == QuotationStatus.REJECTED:
                transition(
                    quotation,
                    QuotationStatus.SUBMITTED,
                    officer,
                    "Penawaran direvisi setelah ditolak Manager",
                )

            quotation.lead_time_days = lead_time_days
            quotation.valid_until = valid_until
            quotation.terms = terms
            update_fields = [
                "lead_time_days",
                "valid_until",
                "terms",
                "updated_at",
            ]
            if attachment is not None:
                quotation.attachment = attachment
                update_fields.append("attachment")
            quotation.save(update_fields=update_fields)

            # Hapus baris harga lama (QuotationItem) sebelum re-create.
            # Nama variabel sengaja tidak mengandung kata model transaksi.
            old_price_rows = quotation.items.all()
            old_price_rows.delete()

        for entry in items:
            QuotationItem.objects.create(
                quotation=quotation,
                pr_item=entry["pr_item"],
                unit_price=entry["unit_price"],
            )
    return quotation


def get_comparison_data(rfq: RFQ) -> dict:
    """
    Bangun data perbandingan penawaran. FR-033.
    Kembalikan dict yang dapat langsung dipakai template.
    """
    rfq_vendors = rfq.rfq_vendors.select_related("vendor").prefetch_related(
        "quotation__items__pr_item__item"
    )
    pr_items = list(rfq.pr.items.select_related("item").order_by("id"))

    vendors = []
    quotations_by_vendor: dict[int, Quotation | None] = {}
    for rv in rfq_vendors:
        q = getattr(rv, "quotation", None)
        vendors.append(rv.vendor)
        quotations_by_vendor[rv.vendor_id] = q

    rows: list[dict] = []
    for pri in pr_items:
        row = {"pr_item": pri, "prices": {}}
        for vendor in vendors:
            q = quotations_by_vendor.get(vendor.pk)
            if q:
                try:
                    qi = q.items.get(pr_item=pri)
                    row["prices"][vendor.pk] = qi.unit_price * pri.qty
                except QuotationItem.DoesNotExist:
                    row["prices"][vendor.pk] = None
            else:
                row["prices"][vendor.pk] = None
        row["lowest"] = min((p for p in row["prices"].values() if p is not None), default=None)
        rows.append(row)

    totals: dict[int, Decimal | None] = {}
    for vendor in vendors:
        prices = [r["prices"].get(vendor.pk) for r in rows]
        if all(p is not None for p in prices):
            totals[vendor.pk] = sum(prices)
        else:
            totals[vendor.pk] = None

    lowest_total = min((v for v in totals.values() if v is not None), default=None)
    return {
        "rfq": rfq,
        "vendors": vendors,
        "rows": rows,
        "totals": totals,
        "lowest_total": lowest_total,
        "quotations_by_vendor": quotations_by_vendor,
    }


def select_quotation(
    quotation: Quotation,
    officer: User,
    justification: str,
    comparison: dict | None = None,
) -> Approval:
    """
    Pilih satu Quotation sebagai pemenang. FR-034 / BR-02.
    Justifikasi wajib jika bukan harga terendah.
    """
    _check_role(officer, Role.OFFICER)

    rfq_vendor = quotation.rfq_vendor
    rfq = rfq_vendor.rfq

    # BR-02: Quotation hanya dari RFQ PR terkait
    if rfq.status not in (RFQStatus.SENT, RFQStatus.CLOSED):
        raise BusinessRuleViolation(
            "Vendor hanya dapat dipilih dari RFQ berstatus SENT atau CLOSED."
        )
    if quotation.status != QuotationStatus.SUBMITTED:
        raise BusinessRuleViolation("Hanya penawaran berstatus SUBMITTED yang dapat dipilih.")
    if Quotation.objects.filter(rfq_vendor__rfq=rfq, status=QuotationStatus.SELECTED).exists():
        raise BusinessRuleViolation("Sudah ada penawaran menunggu approval Manager pada RFQ ini.")

    pr_item_ids = set(rfq.pr.items.values_list("pk", flat=True))
    quoted_ids = set(quotation.items.values_list("pr_item_id", flat=True))
    if pr_item_ids - quoted_ids:
        raise BusinessRuleViolation("Penawaran belum lengkap; isi harga untuk seluruh item PR.")

    # Cek apakah ini harga terendah; justifikasi wajib jika bukan
    if comparison:
        lowest = comparison.get("lowest_total")
        this_total = comparison["totals"].get(rfq_vendor.vendor_id)
        if this_total is None:
            raise BusinessRuleViolation("Total penawaran belum lengkap.")
        if lowest is not None and this_total > lowest and not justification.strip():
            raise BusinessRuleViolation(
                "Justifikasi wajib diisi jika vendor yang dipilih bukan penawar terendah."
            )

    with transaction.atomic():
        quotation.selection_reason = justification
        quotation.save(update_fields=["selection_reason", "updated_at"])
        transition(quotation, QuotationStatus.SELECTED, officer, justification)

        # Tutup RFQ jika masih SENT
        if rfq.status == RFQStatus.SENT:
            transition(rfq, RFQStatus.CLOSED, officer, "Vendor dipilih, RFQ ditutup")

        # FR-035: buat Approval untuk Procurement Manager
        approval = approval_service.create_approval(quotation, required_role=Role.MANAGER, level=1)
    return approval


def approve_vendor_selection(quotation: Quotation, manager: User, note: str = "") -> None:
    """Procurement Manager setujui pemilihan vendor. FR-035."""
    _check_role(manager, Role.MANAGER)
    approval = _require_pending_approval(quotation)
    with transaction.atomic():
        approval_service.decide_approval(approval, manager, approved=True, notes=note)
        transition(quotation, QuotationStatus.APPROVED, manager, note or "Vendor disetujui Manager")
        # Tandai RFQ sebagai AWARDED
        rfq = quotation.rfq_vendor.rfq
        if rfq.status == RFQStatus.CLOSED:
            transition(rfq, RFQStatus.AWARDED, manager, "Vendor dipilih dan disetujui")


def reject_vendor_selection(quotation: Quotation, manager: User, reason: str) -> None:
    """Procurement Manager tolak pemilihan vendor. Quotation kembali ke SUBMITTED."""
    _check_role(manager, Role.MANAGER)
    if not reason.strip():
        raise BusinessRuleViolation("Alasan penolakan wajib diisi.")
    approval = _require_pending_approval(quotation)
    with transaction.atomic():
        approval_service.decide_approval(approval, manager, approved=False, notes=reason)
        transition(quotation, QuotationStatus.REJECTED, manager, reason)


def _require_pending_approval(quotation: Quotation):
    approval = approval_service.get_pending_approval(quotation)
    if approval is None:
        raise BusinessRuleViolation("Tidak ada approval yang menunggu untuk pemilihan vendor ini.")
    return approval
