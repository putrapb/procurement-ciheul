"""
Views: requisitions + dashboard. F-03/04/05.

Semua view tipis: hanya parsing request, panggil service, render. Tanpa logika bisnis.
"""

from __future__ import annotations

import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.approvals.models import Approval, ApprovalStatus
from apps.core.exceptions import BusinessRuleViolation, InvalidTransition
from apps.masterdata.models import Item
from apps.requisitions.models import PRStatus, PurchaseRequest
from services import requisition_service
from services.state_machine import allowed_targets

# ──────────────────────────────────────────────────────────────────────────────
# Dashboard (F-12/F-13/F-15)
# ──────────────────────────────────────────────────────────────────────────────


@login_required
def dashboard(request):
    """FR-061: Dashboard per role — jumlah dokumen + antrean tugas."""
    user = request.user
    role = user.role
    ctx: dict = {"role": role}

    if role == Role.REQUESTER:
        my_prs = PurchaseRequest.objects.filter(requester=user)
        ctx["my_prs"] = my_prs[:10]
        ctx["counts"] = {s: my_prs.filter(status=s).count() for s in PRStatus.values}
        ctx["status_choices"] = PRStatus.choices
        ctx["action_queue"] = my_prs.filter(status__in=[PRStatus.DRAFT, PRStatus.REJECTED])[:5]

    elif role == Role.DEPT_HEAD:
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(PurchaseRequest)
        pr_ids = PurchaseRequest.objects.filter(department=user.department).values_list(
            "pk", flat=True
        )
        pending_approvals = Approval.objects.filter(
            content_type=ct,
            object_id__in=pr_ids,
            status=ApprovalStatus.PENDING,
            required_role=Role.DEPT_HEAD,
        ).select_related()
        ctx["pending_approvals"] = pending_approvals[:10]
        ctx["action_queue"] = pending_approvals[:5]

    elif role == Role.OFFICER:
        from apps.orders.models import POStatus, PurchaseOrder
        from apps.sourcing.models import RFQ

        ctx["prs_to_source"] = PurchaseRequest.objects.filter(status=PRStatus.APPROVED)[:5]
        ctx["rfqs"] = RFQ.objects.filter(created_by=user)[:5]
        ctx["pos_to_send"] = PurchaseOrder.objects.filter(issued_by=user, status=POStatus.APPROVED)[
            :5
        ]

    elif role == Role.MANAGER:
        from django.contrib.contenttypes.models import ContentType

        from apps.orders.models import PurchaseOrder
        from apps.sourcing.models import Quotation

        ct_q = ContentType.objects.get_for_model(Quotation)
        ct_po = ContentType.objects.get_for_model(PurchaseOrder)
        pending = Approval.objects.filter(
            content_type__in=[ct_q, ct_po],
            status=ApprovalStatus.PENDING,
            required_role=Role.MANAGER,
        )
        ctx["pending_approvals"] = pending[:10]
        ctx["action_queue"] = pending[:5]

    elif role == Role.WAREHOUSE:
        from apps.orders.models import POStatus, PurchaseOrder

        ctx["pos_ready"] = PurchaseOrder.objects.filter(
            status__in=[POStatus.SENT, POStatus.PARTIALLY_RECEIVED]
        )[:10]

    elif role == Role.ADMIN:
        from apps.masterdata.models import Vendor

        ctx["total_prs"] = PurchaseRequest.objects.count()
        ctx["total_vendors"] = Vendor.objects.count()
        ctx["total_items"] = Item.objects.count()

    return render(request, "dashboard.html", ctx)


# ──────────────────────────────────────────────────────────────────────────────
# PR List
# ──────────────────────────────────────────────────────────────────────────────


@role_required(Role.REQUESTER, Role.DEPT_HEAD, Role.OFFICER, Role.MANAGER, Role.ADMIN)
def pr_list(request):
    """FR-062: daftar PR dengan filter status dan pencarian nomor."""
    user = request.user
    qs = PurchaseRequest.objects.select_related("requester", "department")

    if user.role == Role.REQUESTER:
        qs = qs.filter(requester=user)
    elif user.role == Role.DEPT_HEAD:
        qs = qs.filter(department=user.department)

    status_filter = request.GET.get("status", "")
    search = request.GET.get("q", "")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(number__icontains=search)

    from django.core.paginator import Paginator

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "requisitions/pr_list.html",
        {
            "page_obj": page,
            "status_choices": PRStatus.choices,
            "status_filter": status_filter,
            "search": search,
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# PR Create
# ──────────────────────────────────────────────────────────────────────────────


@role_required(Role.REQUESTER)
def pr_create(request):
    """FR-020: Requester buat PR baru."""
    items_data = Item.objects.filter(is_active=True)

    if request.method == "POST":
        try:
            dept = request.user.department
            if dept is None:
                raise BusinessRuleViolation("Akun Anda belum memiliki departemen.")
            needed_date = _parse_date(request.POST.get("needed_date"))
            reason = request.POST.get("reason", "").strip()
            items = _parse_items(request)

            pr = requisition_service.create_pr(
                requester=request.user,
                department=dept,
                needed_date=needed_date,
                reason=reason,
                items=items,
            )
            messages.success(request, f"PR {pr.number} berhasil dibuat.")
            return redirect("pr_detail", pk=pr.pk)
        except (BusinessRuleViolation, ValueError) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "requisitions/pr_form.html",
        {
            "items_data": items_data,
            "title": "Buat Purchase Request",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# PR Detail
# ──────────────────────────────────────────────────────────────────────────────


@login_required
def pr_detail(request, pk: int):
    """FR-062: detail PR dengan tab item, approval, riwayat."""
    pr = get_object_or_404(PurchaseRequest.objects.select_related("requester", "department"), pk=pk)
    if not _can_view_pr(pr, request.user):
        raise PermissionDenied
    from services.audit_service import get_logs_for

    audit_logs = get_logs_for(pr)
    from django.contrib.contenttypes.models import ContentType

    from apps.approvals.models import Approval

    approvals = Approval.objects.filter(
        content_type=ContentType.objects.get_for_model(pr),
        object_id=pr.pk,
    ).select_related("approver")

    can_submit = request.user == pr.requester and pr.status == PRStatus.DRAFT
    can_approve_reject = (
        request.user.role == Role.DEPT_HEAD
        and pr.status == PRStatus.SUBMITTED
        and pr.requester_id != request.user.pk
        and request.user.department_id == pr.department_id
    )
    can_revise = request.user == pr.requester and pr.status == PRStatus.REJECTED
    allowed = allowed_targets(pr)
    can_cancel = PRStatus.CANCELLED in allowed and (
        (request.user.role == Role.REQUESTER and request.user == pr.requester)
        or request.user.role in (Role.OFFICER, Role.MANAGER, Role.ADMIN)
    )

    return render(
        request,
        "requisitions/pr_detail.html",
        {
            "pr": pr,
            "audit_logs": audit_logs,
            "approvals": approvals,
            "can_submit": can_submit,
            "can_approve_reject": can_approve_reject,
            "can_revise": can_revise,
            "can_cancel": can_cancel,
            "allowed_targets": allowed,
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# PR Edit
# ──────────────────────────────────────────────────────────────────────────────


@role_required(Role.REQUESTER)
def pr_edit(request, pk: int):
    """FR-021: edit PR DRAFT."""
    pr = get_object_or_404(PurchaseRequest, pk=pk, requester=request.user)
    items_data = Item.objects.filter(is_active=True)

    if request.method == "POST":
        try:
            needed_date = _parse_date(request.POST.get("needed_date"))
            reason = request.POST.get("reason", "").strip()
            items = _parse_items(request)

            requisition_service.update_pr(
                pr, request.user, needed_date=needed_date, reason=reason, items=items
            )
            messages.success(request, f"PR {pr.number} berhasil diperbarui.")
            return redirect("pr_detail", pk=pr.pk)
        except (BusinessRuleViolation, ValueError) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "requisitions/pr_form.html",
        {
            "pr": pr,
            "items_data": items_data,
            "title": f"Edit {pr.number}",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# PR Actions
# ──────────────────────────────────────────────────────────────────────────────


@role_required(Role.REQUESTER)
def pr_delete(request, pk: int):
    """FR-021: hapus PR DRAFT."""
    pr = get_object_or_404(PurchaseRequest, pk=pk, requester=request.user)
    if request.method == "POST":
        try:
            number = pr.number
            requisition_service.delete_pr(pr, request.user)
            messages.success(request, f"PR {number} berhasil dihapus.")
            return redirect("pr_list")
        except BusinessRuleViolation as exc:
            messages.error(request, str(exc))
    return render(request, "requisitions/pr_confirm_delete.html", {"pr": pr})


@role_required(Role.REQUESTER)
def pr_submit(request, pk: int):
    """FR-022: Requester ajukan PR."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method == "POST":
        try:
            requisition_service.submit_pr(pr, request.user)
            messages.success(request, f"PR {pr.number} berhasil diajukan.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("pr_detail", pk=pk)


@role_required(Role.DEPT_HEAD)
def pr_approve(request, pk: int):
    """FR-023: Dept Head setujui PR."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method == "POST":
        note = request.POST.get("note", "")
        try:
            requisition_service.approve_pr(pr, request.user, note)
            messages.success(request, f"PR {pr.number} disetujui.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("pr_detail", pk=pk)


@role_required(Role.DEPT_HEAD)
def pr_reject(request, pk: int):
    """FR-023: Dept Head tolak PR."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            requisition_service.reject_pr(pr, request.user, reason)
            messages.success(request, f"PR {pr.number} ditolak.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("pr_detail", pk=pk)


@role_required(Role.REQUESTER)
def pr_revise(request, pk: int):
    """FR-024: Requester revisi PR yang ditolak."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method == "POST":
        try:
            requisition_service.revise_pr(pr, request.user)
            messages.success(request, f"PR {pr.number} dikembalikan ke Draft untuk revisi.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("pr_detail", pk=pk)


@role_required(Role.REQUESTER, Role.OFFICER, Role.MANAGER, Role.ADMIN)
def pr_cancel(request, pk: int):
    """Batalkan PR."""
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "Dibatalkan oleh user")
        try:
            requisition_service.cancel_pr(pr, request.user, reason)
            messages.success(request, f"PR {pr.number} dibatalkan.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("pr_detail", pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers parsing/otorisasi
# ──────────────────────────────────────────────────────────────────────────────


def _can_view_pr(pr: PurchaseRequest, user) -> bool:
    if user.role in (Role.ADMIN, Role.OFFICER, Role.MANAGER):
        return True
    if user.role == Role.REQUESTER:
        return pr.requester_id == user.pk
    if user.role == Role.DEPT_HEAD:
        return pr.department_id == user.department_id
    return False


def _parse_date(value: str | None) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value or "")
    except (TypeError, ValueError):
        raise BusinessRuleViolation("Tanggal dibutuhkan tidak valid.") from None


def _parse_items(request) -> list[dict]:
    from decimal import Decimal, InvalidOperation

    item_ids = request.POST.getlist("item_id")
    qtys = request.POST.getlist("qty")
    notes_list = request.POST.getlist("notes")

    items: list[dict] = []
    for item_id, qty, note in zip(item_ids, qtys, notes_list, strict=False):
        if not item_id or not qty:
            continue
        try:
            qty_value = Decimal(qty)
        except (InvalidOperation, TypeError, ValueError):
            raise BusinessRuleViolation("Qty item tidak valid.") from None
        items.append(
            {
                "item": get_object_or_404(Item, pk=item_id),
                "qty": qty_value,
                "notes": note,
            }
        )
    return items
