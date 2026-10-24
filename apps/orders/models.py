from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class POStatus(models.TextChoices):
    PENDING_APPROVAL = "PENDING_APPROVAL", "Menunggu Approval"
    APPROVED = "APPROVED", "Disetujui"
    REJECTED = "REJECTED", "Ditolak"
    SENT = "SENT", "Dikirim ke Vendor"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Diterima Sebagian"
    COMPLETED = "COMPLETED", "Selesai"
    CANCELLED = "CANCELLED", "Dibatalkan"


class PurchaseOrder(TimeStampedModel):
    number = models.CharField(max_length=30, unique=True)
    quotation = models.OneToOneField(
        "sourcing.Quotation", on_delete=models.PROTECT, related_name="purchase_order"
    )
    vendor = models.ForeignKey(
        "masterdata.Vendor", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    status = models.CharField(
        max_length=30, choices=POStatus.choices, default=POStatus.PENDING_APPROVAL
    )
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issued_pos"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return self.number


class POItem(models.Model):
    """Snapshot item, qty, dan harga dari quotation saat PO dibuat."""

    po = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey("masterdata.Item", on_delete=models.PROTECT, related_name="po_items")
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["po", "item"], name="uniq_po_item"),
            models.CheckConstraint(condition=models.Q(qty__gt=0), name="po_item_qty_gt_0"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="po_price_gte_0"),
        ]

    def __str__(self) -> str:
        return f"{self.po.number} / {self.item.code}"

    @property
    def subtotal(self):
        return self.qty * self.unit_price
