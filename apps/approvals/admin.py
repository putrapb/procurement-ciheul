"""Admin: approvals app."""

from django.contrib import admin

from .models import Approval


@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "content_type",
        "object_id",
        "level",
        "required_role",
        "status",
        "approver",
        "requested_at",
    )
    list_filter = ("status", "required_role", "content_type")
    search_fields = ("approver__username",)
    readonly_fields = (
        "content_type",
        "object_id",
        "level",
        "required_role",
        "status",
        "approver",
        "notes",
        "requested_at",
        "decided_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False
