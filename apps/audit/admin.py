"""Admin: audit app. AuditLog read-only, append-only (gate L027)."""

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "content_type",
        "object_id",
        "from_status",
        "to_status",
        "user",
        "created_at",
    )
    list_filter = ("content_type",)
    search_fields = ("user__username",)
    readonly_fields = (
        "content_type",
        "object_id",
        "from_status",
        "to_status",
        "user",
        "note",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
