"""
Audit service — helper untuk menulis AuditLog secara manual (di luar state machine).
state_machine.transition() sudah menulis log otomatis; service ini untuk kasus lain.
"""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

from apps.audit.models import AuditLog


def log(
    obj,
    from_status: str,
    to_status: str,
    user,
    note: str = "",
) -> AuditLog:
    """Tulis AuditLog untuk objek. Biasanya dipanggil oleh state_machine.transition()."""
    return AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        from_status=from_status,
        to_status=to_status,
        user=user,
        note=note,
    )


def get_logs_for(obj):
    """Ambil semua AuditLog untuk objek (urutan terbaru dulu)."""
    ct = ContentType.objects.get_for_model(obj)
    return AuditLog.objects.filter(content_type=ct, object_id=obj.pk)
