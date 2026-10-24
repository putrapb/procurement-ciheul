from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Menunggu"
    APPROVED = "APPROVED", "Disetujui"
    REJECTED = "REJECTED", "Ditolak"


class Approval(models.Model):
    """Approval generik untuk PR, Quotation (vendor terpilih), dan PO."""

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    level = models.PositiveSmallIntegerField(default=1)
    required_role = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approvals",
    )
    notes = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "level"],
                condition=models.Q(status="PENDING"),
                name="uniq_pending_approval_per_object_level",
            )
        ]

    def __str__(self) -> str:
        return f"Approval #{self.pk} ({self.status})"
