"""
Requisition service — logika bisnis Purchase Request (F-03, F-04, F-05).

FR yang tercakup:
  FR-020  buat PR dengan nomor otomatis, ≥ 1 item (qty > 0)
  FR-021  PR DRAFT dapat diedit/dihapus oleh pembuatnya
  FR-022  submit → SUBMITTED + buat Approval PENDING untuk Dept Head
  FR-023  Dept Head approve/reject (alasan wajib saat reject); approver ≠ requester (BR-01)
  FR-024  REJECTED → DRAFT (revisi) oleh requester
  FR-025  Officer tandai PR APPROVED → IN_SOURCING saat RFQ dibuat

BR yang tercakup:
  BR-01   segregation of duties — requester ≠ approver
  BR-06   dokumen final tidak dapat diubah (kecuali revisi yang diizinkan)
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db import transaction

from apps.accounts.models import Role, User
from apps.approvals.models import Approval, ApprovalStatus
from apps.core.exceptions import BusinessRuleViolation
from apps.masterdata.models import Department
from apps.requisitions.models import PRItem, PRStatus, PurchaseRequest
from services import approval_service
from services.numbering import next_number
from services.state_machine import transition

# ──────────────────────────────────────────────────────────────────────────────
# Buat dan edit PR
# ──────────────────────────────────────────────────────────────────────────────


def create_pr(
    requester: User,
    department: Department,
    needed_date: datetime.date,
    reason: str,
    items: list[dict[str, Any]],
) -> PurchaseRequest:
    """
    Buat PR baru berstatus DRAFT. F-03 / FR-020.

    `items` = [{"item": Item, "qty": Decimal, "notes": str}, ...]
    qty harus > 0 dan minimal 1 item.
    """
    _check_role(requester, Role.REQUESTER)
    _validate_department(requester, department)
    if not reason or not reason.strip():
        raise BusinessRuleViolation("Alasan pengadaan wajib diisi.")
    _validate_items(items)

    with transaction.atomic():
        number = next_number("PR")
        pr = PurchaseRequest.objects.create(
            number=number,
            requester=requester,
            department=department,
            needed_date=needed_date,
            reason=reason,
            status=PRStatus.DRAFT,
        )
        for entry in items:
            PRItem.objects.create(
                pr=pr,
                item=entry["item"],
                qty=entry["qty"],
                notes=entry.get("notes", ""),
            )
    return pr


def update_pr(
    pr: PurchaseRequest,
    requester: User,
    *,
    needed_date: datetime.date | None = None,
    reason: str | None = None,
    items: list[dict[str, Any]] | None = None,
) -> PurchaseRequest:
    """
    Edit PR yang masih DRAFT. FR-021 / BR-06.
    Hanya pembuat yang boleh mengedit.
    """
    if pr.status != PRStatus.DRAFT:
        raise BusinessRuleViolation("Hanya PR berstatus DRAFT yang dapat diedit.")
    if pr.requester_id != requester.pk:
        raise BusinessRuleViolation("Hanya pembuat PR yang boleh mengeditnya.")
    if reason is not None and not reason.strip():
        raise BusinessRuleViolation("Alasan pengadaan wajib diisi.")
    if items is not None:
        _validate_items(items)

    with transaction.atomic():
        if needed_date is not None:
            pr.needed_date = needed_date
        if reason is not None:
            pr.reason = reason
        pr.save(update_fields=["needed_date", "reason", "updated_at"])

        if items is not None:
            pr.items.all().delete()
            for entry in items:
                PRItem.objects.create(
                    pr=pr,
                    item=entry["item"],
                    qty=entry["qty"],
                    notes=entry.get("notes", ""),
                )
    return pr


def delete_pr(pr: PurchaseRequest, requester: User) -> None:
    """
    Hapus PR DRAFT. FR-021.
    Hanya PR DRAFT yang boleh dihapus (gate L026).
    """
    if pr.status != PRStatus.DRAFT:
        raise BusinessRuleViolation("Hanya PR berstatus DRAFT yang dapat dihapus.")
    if pr.requester_id != requester.pk:
        raise BusinessRuleViolation("Hanya pembuat PR yang boleh menghapusnya.")
    with transaction.atomic():
        pr.items.all().delete()
        pr.delete()


# ──────────────────────────────────────────────────────────────────────────────
# Alur status
# ──────────────────────────────────────────────────────────────────────────────


def submit_pr(pr: PurchaseRequest, requester: User) -> Approval:
    """
    Submit PR DRAFT → SUBMITTED + buat Approval PENDING untuk Dept Head. FR-022.
    """
    if pr.requester_id != requester.pk:
        raise BusinessRuleViolation("Hanya pembuat PR yang boleh mengajukannya.")
    if not pr.items.exists():
        raise BusinessRuleViolation("PR harus memiliki minimal 1 item sebelum diajukan.")
    with transaction.atomic():
        transition(pr, PRStatus.SUBMITTED, requester, "Diajukan oleh requester")
        approval = Approval.objects.create(
            content_type=_ct(pr),
            object_id=pr.pk,
            level=1,
            required_role=Role.DEPT_HEAD,
            status=ApprovalStatus.PENDING,
        )
    return approval


def approve_pr(pr: PurchaseRequest, approver: User, note: str = "") -> None:
    """
    Dept Head setujui PR SUBMITTED → APPROVED. FR-023 / BR-01.
    Approver tidak boleh sama dengan requester.
    """
    _check_segregation(pr, approver)
    _check_role(approver, Role.DEPT_HEAD)
    _check_department(pr, approver)
    approval = _get_pending_approval(pr)
    with transaction.atomic():
        approval_service.decide_approval(approval, approver, approved=True, notes=note)
        transition(pr, PRStatus.APPROVED, approver, note or "Disetujui Dept Head")


def reject_pr(pr: PurchaseRequest, approver: User, reason: str) -> None:
    """
    Dept Head tolak PR SUBMITTED → REJECTED. FR-023 / BR-01.
    Alasan wajib diisi.
    """
    if not reason or not reason.strip():
        raise BusinessRuleViolation("Alasan penolakan wajib diisi.")
    _check_segregation(pr, approver)
    _check_role(approver, Role.DEPT_HEAD)
    _check_department(pr, approver)
    approval = _get_pending_approval(pr)
    with transaction.atomic():
        approval_service.decide_approval(approval, approver, approved=False, notes=reason)
        transition(pr, PRStatus.REJECTED, approver, reason)


def revise_pr(pr: PurchaseRequest, requester: User) -> None:
    """
    Kembalikan PR REJECTED ke DRAFT (revisi). FR-024.
    """
    if pr.requester_id != requester.pk:
        raise BusinessRuleViolation("Hanya pembuat PR yang boleh merevisi PR yang ditolak.")
    with transaction.atomic():
        transition(pr, PRStatus.DRAFT, requester, "Dikembalikan ke draft untuk revisi")


def mark_in_sourcing(pr: PurchaseRequest, officer: User) -> None:
    """
    Tandai PR APPROVED → IN_SOURCING saat RFQ dibuat. FR-025.
    Dipanggil oleh sourcing_service.
    """
    _check_role(officer, Role.OFFICER)
    with transaction.atomic():
        transition(pr, PRStatus.IN_SOURCING, officer, "RFQ dibuat, PR dalam proses sourcing")


def cancel_pr(pr: PurchaseRequest, user: User, reason: str = "") -> None:
    """Batalkan PR. Hanya bisa dari DRAFT/SUBMITTED/APPROVED/IN_SOURCING."""
    if user.role == Role.REQUESTER:
        if pr.requester_id != user.pk:
            raise BusinessRuleViolation("Hanya pembuat PR yang boleh membatalkan PR ini.")
    elif user.role not in (Role.OFFICER, Role.MANAGER, Role.ADMIN):
        raise BusinessRuleViolation(
            "Hanya Requester/Officer/Manager/Admin yang dapat membatalkan PR."
        )

    with transaction.atomic():
        transition(pr, PRStatus.CANCELLED, user, reason or "Dibatalkan")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internal
# ──────────────────────────────────────────────────────────────────────────────


def _check_segregation(pr: PurchaseRequest, approver: User) -> None:
    """BR-01: requester tidak boleh menjadi approver PR miliknya sendiri."""
    if pr.requester_id == approver.pk:
        raise BusinessRuleViolation(
            "Pembuat PR tidak boleh menyetujui PR miliknya sendiri (BR-01)."
        )


def _check_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise BusinessRuleViolation(
            f"Aksi ini memerlukan role {'/'.join(roles)}, bukan {user.role}."
        )


def _check_department(pr: PurchaseRequest, approver: User) -> None:
    """FR-023: Dept Head hanya memutuskan PR pada departemennya sendiri."""
    if approver.department_id != pr.department_id:
        raise BusinessRuleViolation(
            "Dept Head hanya dapat menyetujui PR pada departemennya sendiri."
        )


def _validate_department(requester: User, department: Department) -> None:
    if requester.department_id != department.pk:
        raise BusinessRuleViolation("PR hanya dapat dibuat untuk departemen tempat Anda terdaftar.")


def _validate_items(items: list[dict[str, Any]]) -> None:
    if not items:
        raise BusinessRuleViolation("PR harus memiliki minimal 1 item.")
    seen: set[int] = set()
    for entry in items:
        item = entry.get("item")
        qty = entry.get("qty")
        if item is None:
            raise BusinessRuleViolation("Item PR tidak valid.")
        if item.pk in seen:
            raise BusinessRuleViolation(f"Item {item.code} duplikat dalam PR.")
        seen.add(item.pk)
        if qty is None or qty <= 0:
            raise BusinessRuleViolation(f"Qty item {item.code} harus > 0.")


def _get_pending_approval(pr: PurchaseRequest) -> Approval:
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(pr)
    try:
        return Approval.objects.get(
            content_type=ct,
            object_id=pr.pk,
            status=ApprovalStatus.PENDING,
        )
    except Approval.DoesNotExist:
        raise BusinessRuleViolation("Tidak ada approval yang menunggu untuk PR ini.") from None


def _ct(obj):
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.get_for_model(obj)
