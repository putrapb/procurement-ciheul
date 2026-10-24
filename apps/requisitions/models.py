from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class PRStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Diajukan"
    APPROVED = "APPROVED", "Disetujui"
    REJECTED = "REJECTED", "Ditolak"
    IN_SOURCING = "IN_SOURCING", "Dalam Sourcing"
    PO_ISSUED = "PO_ISSUED", "PO Terbit"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Diterima Sebagian"
    COMPLETED = "COMPLETED", "Selesai"
    CANCELLED = "CANCELLED", "Dibatalkan"


class PurchaseRequest(TimeStampedModel):
    number = models.CharField(max_length=30, unique=True)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchase_requests"
    )
    department = models.ForeignKey(
        "masterdata.Department", on_delete=models.PROTECT, related_name="purchase_requests"
    )
    needed_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=30, choices=PRStatus.choices, default=PRStatus.DRAFT)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return self.number


class PRItem(models.Model):
    pr = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey("masterdata.Item", on_delete=models.PROTECT, related_name="pr_items")
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["pr", "item"], name="uniq_pr_item"),
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="pr_item_qty_gt_0"),
        ]

    def __str__(self) -> str:
        return f"{self.pr.number} / {self.item.code}"
