"""Admin: orders app. F-09/10/14."""

from django.contrib import admin

from .models import POItem, PurchaseOrder


class POItemInline(admin.TabularInline):
    model = POItem
    extra = 0
    readonly_fields = ("item", "qty", "unit_price")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "vendor",
        "status",
        "total_amount",
        "issued_by",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("number", "vendor__code")
    readonly_fields = (
        "number",
        "quotation",
        "vendor",
        "status",
        "total_amount",
        "issued_by",
        "created_at",
        "updated_at",
    )
    inlines = [POItemInline]

    def has_delete_permission(self, request, obj=None):
        return False
