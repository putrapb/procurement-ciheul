"""Satu-satunya tempat status dokumen boleh berubah (gate L020).

Setiap transisi divalidasi terhadap TRANSITIONS dan otomatis menulis AuditLog
dalam transaksi yang sama (gate L022).
"""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.audit.models import AuditLog
from apps.core.exceptions import InvalidTransition

TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "PurchaseRequest": {
        "DRAFT": {"SUBMITTED", "CANCELLED"},
        "SUBMITTED": {"APPROVED", "REJECTED", "CANCELLED"},
        "REJECTED": {"DRAFT"},
        "APPROVED": {"IN_SOURCING", "CANCELLED"},
        "IN_SOURCING": {"PO_ISSUED", "CANCELLED"},
        "PO_ISSUED": {"PARTIALLY_RECEIVED", "COMPLETED"},
        "PARTIALLY_RECEIVED": {"COMPLETED"},
    },
    "RFQ": {
        "DRAFT": {"SENT", "CANCELLED"},
        "SENT": {"CLOSED", "CANCELLED"},
        "CLOSED": {"AWARDED"},
    },
    "Quotation": {
        "SUBMITTED": {"SELECTED"},
        "SELECTED": {"APPROVED", "REJECTED"},
        "REJECTED": {"SUBMITTED"},
    },
    "PurchaseOrder": {
        "PENDING_APPROVAL": {"APPROVED", "REJECTED", "CANCELLED"},
        "REJECTED": {"PENDING_APPROVAL", "CANCELLED"},
        "APPROVED": {"SENT", "CANCELLED"},
        "SENT": {"PARTIALLY_RECEIVED", "COMPLETED"},
        "PARTIALLY_RECEIVED": {"COMPLETED"},
    },
}


def allowed_targets(obj) -> set[str]:
    """Status tujuan yang sah dari status objek saat ini (berguna untuk menampilkan tombol aksi)."""
    return TRANSITIONS.get(type(obj).__name__, {}).get(obj.status, set())


def transition(obj, to_status: str, user, note: str = "") -> None:
    """Ubah status `obj` ke `to_status` + tulis AuditLog secara atomik."""
    model_name = type(obj).__name__
    table = TRANSITIONS.get(model_name)
    if table is None:
        raise InvalidTransition(f"{model_name} tidak memiliki state machine")

    from_status = obj.status
    if to_status not in table.get(from_status, set()):
        raise InvalidTransition(f"{model_name}: {from_status} -> {to_status} tidak diizinkan")

    with transaction.atomic():
        obj.status = to_status
        obj.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(
            content_type=ContentType.objects.get_for_model(obj),
            object_id=obj.pk,
            from_status=from_status,
            to_status=to_status,
            user=user,
            note=note,
        )
