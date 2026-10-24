from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class RFQStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SENT = "SENT", "Terkirim"
    CLOSED = "CLOSED", "Ditutup"
    AWARDED = "AWARDED", "Pemenang Dipilih"
    CANCELLED = "CANCELLED", "Dibatalkan"


class QuotationStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Masuk"
    SELECTED = "SELECTED", "Dipilih (menunggu approval)"
    APPROVED = "APPROVED", "Disetujui"
    REJECTED = "REJECTED", "Ditolak"


class RFQ(TimeStampedModel):
    number = models.CharField(max_length=30, unique=True)
    pr = models.ForeignKey(
        "requisitions.PurchaseRequest", on_delete=models.PROTECT, related_name="rfqs"
    )
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=RFQStatus.choices, default=RFQStatus.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rfqs"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return self.number


class RFQVendor(models.Model):
    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name="rfq_vendors")
    vendor = models.ForeignKey(
        "masterdata.Vendor", on_delete=models.PROTECT, related_name="rfq_vendors"
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["rfq", "vendor"], name="uniq_rfq_vendor")]

    def __str__(self) -> str:
        return f"{self.rfq.number} -> {self.vendor.code}"


class Quotation(TimeStampedModel):
    rfq_vendor = models.OneToOneField(RFQVendor, on_delete=models.PROTECT, related_name="quotation")
    lead_time_days = models.PositiveIntegerField(default=0)
    valid_until = models.DateField(null=True, blank=True)
    terms = models.TextField(blank=True)
    attachment = models.FileField(upload_to="quotations/", blank=True)
    status = models.CharField(
        max_length=20, choices=QuotationStatus.choices, default=QuotationStatus.SUBMITTED
    )
    selection_reason = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Quotation {self.rfq_vendor}"


class QuotationItem(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="items")
    pr_item = models.ForeignKey(
        "requisitions.PRItem", on_delete=models.PROTECT, related_name="quotation_items"
    )
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["quotation", "pr_item"], name="uniq_quotation_pr_item"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="quo_price_gte_0"),
        ]

    def __str__(self) -> str:
        return f"{self.quotation_id} / {self.pr_item_id}"
