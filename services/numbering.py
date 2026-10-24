"""Generator nomor dokumen berformat PREFIX-YYYYMM-NNNN, aman terhadap race condition."""

from django.db import transaction
from django.utils import timezone

from apps.core.models import DocumentSequence


def next_number(prefix: str) -> str:
    period = timezone.localdate().strftime("%Y%m")
    key = f"{prefix}-{period}"
    with transaction.atomic():
        seq, _ = DocumentSequence.objects.select_for_update().get_or_create(key=key)
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
    return f"{key}-{seq.last_value:04d}"
