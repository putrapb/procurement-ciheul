"""
Approval service — generik untuk PR, Quotation, dan PO.

FR yang tercakup:
  FR-023  Dept Head approve/reject PR
  FR-035  Procurement Manager approve pemilihan vendor (Quotation)
  FR-041  Procurement Manager approve/reject PO
"""

from __future__ import annotations

from apps.accounts.models import User
from apps.approvals.models import Approval, ApprovalStatus
from apps.core.exceptions import BusinessRuleViolation
from services.state_machine import set_approval_decision


def get_pending_approval(obj) -> Approval:
    """Ambil Approval PENDING untuk objek. Raise BusinessRuleViolation jika tidak ada."""
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(obj)
    try:
        return Approval.objects.get(
            content_type=ct,
            object_id=obj.pk,
            status=ApprovalStatus.PENDING,
        )
    except Approval.DoesNotExist:
        raise BusinessRuleViolation("Tidak ada approval yang menunggu untuk objek ini.") from None


def create_approval(obj, required_role: str, level: int = 1) -> Approval:
    """Buat Approval PENDING baru untuk objek."""
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(obj)
    return Approval.objects.create(
        content_type=ct,
        object_id=obj.pk,
        level=level,
        required_role=required_role,
        status=ApprovalStatus.PENDING,
    )


def decide_approval(
    approval: Approval,
    approver: User,
    approved: bool,
    notes: str = "",
) -> Approval:
    """
    Set approval ke APPROVED atau REJECTED.
    Cek role approver sesuai required_role.
    """
    if approval.status != ApprovalStatus.PENDING:
        raise BusinessRuleViolation("Approval ini sudah diputuskan.")
    if approver.role != approval.required_role:
        raise BusinessRuleViolation(
            f"Aksi ini memerlukan role {approval.required_role}, bukan {approver.role}."
        )
    if not approved and not (notes and notes.strip()):
        raise BusinessRuleViolation("Alasan penolakan wajib diisi.")

    target = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    # Mutasi status Approval dipusatkan di state_machine (gate L020).
    set_approval_decision(approval, target, approver, notes)
    return approval
