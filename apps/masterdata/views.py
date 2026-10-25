"""Views: masterdata. F-02. Read-only list — CRUD lewat Django Admin."""

from django.shortcuts import render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required

from .models import Department, Item, Vendor


@role_required(Role.ADMIN)
def department_list(request):
    """Daftar Department. CRUD via admin."""
    depts = Department.objects.all()
    return render(request, "masterdata/department_list.html", {"departments": depts})


@role_required(Role.ADMIN)
def item_list(request):
    """Daftar Item. CRUD via admin."""
    items = Item.objects.all()
    return render(request, "masterdata/item_list.html", {"items": items})


@role_required(Role.ADMIN)
def vendor_list(request):
    """Daftar Vendor. CRUD via admin."""
    vendors = Vendor.objects.all()
    return render(request, "masterdata/vendor_list.html", {"vendors": vendors})
