"""Admin: masterdata app. F-02."""

from django.contrib import admin

from .models import Department, Item, Vendor


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "uom", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "contact_person", "email", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "email")
