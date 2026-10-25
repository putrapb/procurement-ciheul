"""Admin: accounts app. F-01."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "get_full_name", "role", "department", "is_active")
    list_filter = ("role", "is_active", "department")
    search_fields = ("username", "first_name", "last_name", "email")
    fieldsets = BaseUserAdmin.fieldsets + (  # type: ignore[operator]
        ("Role & Departemen", {"fields": ("role", "department")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (  # type: ignore[operator]
        ("Role & Departemen", {"fields": ("role", "department")}),
    )
