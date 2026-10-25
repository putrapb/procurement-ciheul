"""Admin: sourcing app. F-06/07/08."""

from django.contrib import admin

from .models import RFQ, Quotation, QuotationItem, RFQVendor


class RFQVendorInline(admin.TabularInline):
    model = RFQVendor
    extra = 0
    readonly_fields = ("vendor", "sent_at")


@admin.register(RFQ)
class RFQAdmin(admin.ModelAdmin):
    list_display = ("number", "pr", "status", "due_date", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("number", "pr__number")
    readonly_fields = ("number", "pr", "status", "created_by", "created_at", "updated_at")
    inlines = [RFQVendorInline]

    def has_delete_permission(self, request, obj=None):
        return False


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0
    readonly_fields = ("pr_item", "unit_price")


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("pk", "rfq_vendor", "status", "valid_until", "created_at")
    list_filter = ("status",)
    search_fields = ("rfq_vendor__rfq__number",)
    readonly_fields = ("rfq_vendor", "status", "selection_reason", "created_at", "updated_at")
    inlines = [QuotationItemInline]

    def has_delete_permission(self, request, obj=None):
        return False
