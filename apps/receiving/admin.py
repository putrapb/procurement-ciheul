"""Admin: receiving app. F-11."""

from django.contrib import admin

from .models import GoodsReceipt, GRItem


class GRItemInline(admin.TabularInline):
    model = GRItem
    extra = 0
    readonly_fields = ("po_item", "qty_received", "condition", "notes")


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "po",
        "delivery_note_no",
        "received_date",
        "received_by",
        "created_at",
    )
    list_filter = ()
    search_fields = ("number", "po__number", "delivery_note_no")
    readonly_fields = ("number", "po", "received_by", "created_at", "updated_at")
    inlines = [GRItemInline]

    def has_delete_permission(self, request, obj=None):
        return False
