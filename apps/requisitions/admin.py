"""Admin: requisitions app. F-03/04/05."""

from django.contrib import admin

from .models import PRItem, PurchaseRequest


class PRItemInline(admin.TabularInline):
    model = PRItem
    extra = 0
    readonly_fields = ("item", "qty", "notes")


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ("number", "requester", "department", "status", "needed_date", "created_at")
    list_filter = ("status", "department")
    search_fields = ("number", "requester__username", "reason")
    readonly_fields = ("number", "requester", "department", "status", "created_at", "updated_at")
    inlines = [PRItemInline]

    def has_delete_permission(self, request, obj=None):
        # Hanya PR DRAFT yang boleh dihapus (gate L026); admin tidak meng-expose hard delete
        return False
