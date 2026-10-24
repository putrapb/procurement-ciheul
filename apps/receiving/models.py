from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Condition(models.TextChoices):
    OK = "OK", "Baik"
    DAMAGED = "DAMAGED", "Rusak"


class GoodsReceipt(TimeStampedModel):
    """Catatan penerimaan barang. BUKAN modul stok/gudang (out of scope)."""

    number = models.CharField(max_length=30, unique=True)
    po = models.ForeignKey(
        "orders.PurchaseOrder", on_delete=models.PROTECT, related_name="receipts"
    )
    delivery_note_no = models.CharField("no. surat jalan", max_length=50)
    received_date = models.DateField()
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="receipts"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number


class GRItem(models.Model):
    gr = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="items")
    po_item = models.ForeignKey("orders.POItem", on_delete=models.PROTECT, related_name="gr_items")
    qty_received = models.DecimalField(max_digits=12, decimal_places=2)
    condition = models.CharField(max_length=10, choices=Condition.choices, default=Condition.OK)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["gr", "po_item"], name="uniq_gr_po_item"),
            models.CheckConstraint(condition=models.Q(qty_received__gt=0), name="gr_qty_gt_0"),
        ]

    def __str__(self) -> str:
        return f"{self.gr.number} / {self.po_item_id}"
