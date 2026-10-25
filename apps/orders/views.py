"""
Views: orders (PurchaseOrder). F-09/10/14.
Semua view tipis — logika di order_service.
"""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.core.exceptions import BusinessRuleViolation, InvalidTransition
from apps.orders.models import POStatus, PurchaseOrder
from apps.sourcing.models import Quotation
from services import order_service
from services.audit_service import get_logs_for
from services.state_machine import allowed_targets


@role_required(Role.OFFICER, Role.MANAGER, Role.WAREHOUSE, Role.ADMIN)
def po_list(request):
    """F-15: daftar PO dengan filter status, pencarian, dan pagination."""
    from django.core.paginator import Paginator
    from django.db.models import Q

    qs = PurchaseOrder.objects.select_related("vendor", "issued_by")
    status_filter = request.GET.get("status", "")
    search = request.GET.get("q", "")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(Q(number__icontains=search) | Q(vendor__name__icontains=search))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "orders/po_list.html",
        {
            "pos": page,
            "page_obj": page,
            "status_choices": POStatus.choices,
            "status_filter": status_filter,
            "search": search,
        },
    )


@role_required(Role.OFFICER)
def po_create(request, quotation_pk: int):
    """FR-040: Officer terbitkan PO dari Quotation APPROVED."""
    quotation = get_object_or_404(Quotation, pk=quotation_pk)
    if request.method == "POST":
        try:
            po = order_service.create_po(quotation, request.user)
            messages.success(request, f"PO {po.number} berhasil diterbitkan.")
            return redirect("po_detail", pk=po.pk)
        except BusinessRuleViolation as exc:
            messages.error(request, str(exc))
    return render(request, "orders/po_confirm_create.html", {"quotation": quotation})


@role_required(Role.OFFICER, Role.MANAGER, Role.WAREHOUSE)
def po_detail(request, pk: int):
    """Detail PO dengan item, approval, dan riwayat."""
    po = get_object_or_404(
        PurchaseOrder.objects.select_related("vendor", "quotation", "issued_by"),
        pk=pk,
    )
    audit_logs = get_logs_for(po)
    from django.contrib.contenttypes.models import ContentType

    from apps.approvals.models import Approval

    approvals = Approval.objects.filter(
        content_type=ContentType.objects.get_for_model(po),
        object_id=po.pk,
    ).select_related("approver")

    allowed = allowed_targets(po)
    can_cancel = POStatus.CANCELLED in allowed and request.user.role in (
        Role.OFFICER,
        Role.MANAGER,
        Role.ADMIN,
    )
    return render(
        request,
        "orders/po_detail.html",
        {
            "po": po,
            "audit_logs": audit_logs,
            "approvals": approvals,
            "allowed_targets": allowed,
            "can_cancel": can_cancel,
        },
    )


@role_required(Role.MANAGER)
def po_approve(request, pk: int):
    """FR-041: Manager setujui PO."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        note = request.POST.get("note", "")
        try:
            order_service.approve_po(po, request.user, note)
            messages.success(request, f"PO {po.number} disetujui.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("po_detail", pk=pk)


@role_required(Role.MANAGER)
def po_reject(request, pk: int):
    """FR-041: Manager tolak PO."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            order_service.reject_po(po, request.user, reason)
            messages.success(request, f"PO {po.number} ditolak.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("po_detail", pk=pk)


@role_required(Role.OFFICER)
def po_send(request, pk: int):
    """FR-042: Officer kirim PO ke vendor."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        try:
            order_service.send_po(po, request.user)
            messages.success(request, f"PO {po.number} berhasil dikirim ke vendor.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("po_detail", pk=pk)


@role_required(Role.OFFICER)
def po_resubmit(request, pk: int):
    """FR-043: Officer ajukan ulang PO yang ditolak."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        note = request.POST.get("note", "")
        try:
            order_service.resubmit_po(po, request.user, note)
            messages.success(request, f"PO {po.number} diajukan ulang.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("po_detail", pk=pk)


@role_required(Role.OFFICER, Role.MANAGER, Role.ADMIN)
def po_cancel(request, pk: int):
    """Batalkan PO."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "Dibatalkan")
        try:
            order_service.cancel_po(po, request.user, reason)
            messages.success(request, f"PO {po.number} dibatalkan.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("po_detail", pk=pk)


@role_required(Role.OFFICER, Role.MANAGER)
def po_print(request, pk: int):
    """FR-042: Cetak PO."""
    po = get_object_or_404(PurchaseOrder.objects.select_related("vendor", "quotation"), pk=pk)
    return render(request, "orders/po_print.html", {"po": po})
