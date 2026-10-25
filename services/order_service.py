"""
Order service — logika bisnis Purchase Order (F-09, F-10, F-14).

FR yang tercakup:
  FR-040  Setelah vendor di-approve, Officer terbitkan PO otomatis dari quotation
  FR-041  PO PENDING_APPROVAL → APPROVED (Manager) atau REJECTED
  FR-042  PO APPROVED dapat ditandai SENT dan dicetak
  FR-043  PO REJECTED kembali ke Officer untuk revisi atau pembatalan

BR yang tercakup:
  BR-03  Total PO = sum(qty × unit_price) dari quotation terpilih
  BR-04  Harga dan qty PO tidak dapat diubah setelah APPROVED
"""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models import Role, User
from apps.core.exceptions import BusinessRuleViolation
from apps.orders.models import POItem, POStatus, PurchaseOrder
from apps.requisitions.models import PRStatus
from apps.sourcing.models import QuotationStatus, RFQStatus
from services import approval_service
from services.numbering import next_number
from services.state_machine import transition


def _check_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise BusinessRuleViolation(
            f"Aksi ini memerlukan role {'/'.join(roles)}, bukan {user.role}."
        )


# ──────────────────────────────────────────────────────────────────────────────
# Buat PO
# ──────────────────────────────────────────────────────────────────────────────


def create_po(quotation, officer: User) -> PurchaseOrder:
    """
    Terbitkan PO dari Quotation APPROVED. FR-040 / BR-03.

    POItem adalah snapshot dari QuotationItem (qty dari PRItem, harga dari QuotationItem).
    """
    _check_role(officer, Role.OFFICER)
    if quotation.status != QuotationStatus.APPROVED:
        raise BusinessRuleViolation(
            "PO hanya dapat dibuat dari Quotation yang sudah disetujui Manager."
        )
    rfq = quotation.rfq_vendor.rfq
    if rfq.status != RFQStatus.AWARDED:
        raise BusinessRuleViolation("PO hanya dapat dibuat dari RFQ berstatus AWARDED.")

    # Pastikan belum ada PO untuk quotation ini
    if hasattr(quotation, "purchase_order"):
        raise BusinessRuleViolation("PO untuk quotation ini sudah ada.")

    quotation_items = list(quotation.items.select_related("pr_item__item").all())
    if not quotation_items:
        raise BusinessRuleViolation("Quotation tidak memiliki item untuk diterbitkan PO.")
    pr_item_ids = set(rfq.pr.items.values_list("pk", flat=True))
    quoted_ids = {qi.pr_item_id for qi in quotation_items}
    if pr_item_ids - quoted_ids:
        raise BusinessRuleViolation("Quotation belum lengkap untuk seluruh item PR.")

    with transaction.atomic():
        vendor = quotation.rfq_vendor.vendor
        number = next_number("PO")

        # BR-03: hitung total
        total = sum(qi.unit_price * qi.pr_item.qty for qi in quotation_items)
        po = PurchaseOrder.objects.create(
            number=number,
            quotation=quotation,
            vendor=vendor,
            status=POStatus.PENDING_APPROVAL,
            total_amount=total,
            issued_by=officer,
        )
        # Snapshot item dari quotation
        for qi in quotation_items:
            POItem.objects.create(
                po=po,
                item=qi.pr_item.item,
                qty=qi.pr_item.qty,
                unit_price=qi.unit_price,
            )
        # Buat Approval untuk Manager
        approval_service.create_approval(po, required_role=Role.MANAGER, level=1)
    return po


# ──────────────────────────────────────────────────────────────────────────────
# Alur status PO
# ──────────────────────────────────────────────────────────────────────────────


def approve_po(po: PurchaseOrder, manager: User, note: str = "") -> None:
    """Manager setujui PO PENDING_APPROVAL → APPROVED. FR-041 / BR-04."""
    _check_role(manager, Role.MANAGER)
    approval = approval_service.get_pending_approval(po)
    with transaction.atomic():
        approval_service.decide_approval(approval, manager, approved=True, notes=note)
        transition(po, POStatus.APPROVED, manager, note or "PO disetujui Manager")


def reject_po(po: PurchaseOrder, manager: User, reason: str) -> None:
    """Manager tolak PO → REJECTED. FR-041/FR-043."""
    _check_role(manager, Role.MANAGER)
    if not reason.strip():
        raise BusinessRuleViolation("Alasan penolakan wajib diisi.")
    approval = approval_service.get_pending_approval(po)
    with transaction.atomic():
        approval_service.decide_approval(approval, manager, approved=False, notes=reason)
        transition(po, POStatus.REJECTED, manager, reason)


def send_po(po: PurchaseOrder, officer: User) -> None:
    """Tandai PO APPROVED → SENT (dikirim ke vendor). FR-042. Juga update PR → PO_ISSUED."""
    _check_role(officer, Role.OFFICER)
    if po.status != POStatus.APPROVED:
        raise BusinessRuleViolation("Hanya PO berstatus APPROVED yang dapat dikirim.")
    with transaction.atomic():
        transition(po, POStatus.SENT, officer, "PO dikirim ke vendor")
        # Update PR status ke PO_ISSUED (dari IN_SOURCING)
        pr = po.quotation.rfq_vendor.rfq.pr
        if pr.status == PRStatus.IN_SOURCING:
            transition(pr, PRStatus.PO_ISSUED, officer, "PO diterbitkan dan dikirim ke vendor")


def resubmit_po(po: PurchaseOrder, officer: User, note: str = "") -> None:
    """
    Revisi PO REJECTED → PENDING_APPROVAL (kembali ke antrian approval). FR-043.
    Buat ulang Approval baru karena yang lama sudah REJECTED.
    """
    _check_role(officer, Role.OFFICER)
    if po.status != POStatus.REJECTED:
        raise BusinessRuleViolation("Hanya PO berstatus REJECTED yang dapat direvisi.")
    with transaction.atomic():
        transition(po, POStatus.PENDING_APPROVAL, officer, note or "PO direvisi dan diajukan ulang")
        approval_service.create_approval(po, required_role=Role.MANAGER, level=1)


def cancel_po(po: PurchaseOrder, user: User, reason: str = "") -> None:
    """Batalkan PO dari PENDING_APPROVAL/REJECTED/APPROVED."""
    _check_role(user, Role.OFFICER, Role.MANAGER, Role.ADMIN)
    if po.status not in (POStatus.PENDING_APPROVAL, POStatus.REJECTED, POStatus.APPROVED):
        raise BusinessRuleViolation(f"PO berstatus {po.status} tidak dapat dibatalkan.")
    with transaction.atomic():
        transition(po, POStatus.CANCELLED, user, reason or "Dibatalkan")


def check_po_immutable(po: PurchaseOrder) -> None:
    """
    BR-04: Validasi bahwa PO yang sudah APPROVED tidak dapat diubah harga/qty-nya.
    Dipanggil dari view sebelum memproses form edit item.
    """
    if po.status not in (POStatus.PENDING_APPROVAL, POStatus.REJECTED):
        raise BusinessRuleViolation(
            "Harga dan qty PO tidak dapat diubah setelah status APPROVED (BR-04)."
        )
