"""
Views: receiving (GoodsReceipt). F-11.
Semua view tipis — logika di receiving_service.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.core.exceptions import BusinessRuleViolation
from apps.orders.models import POStatus, PurchaseOrder
from apps.receiving.models import Condition, GoodsReceipt
from services import receiving_service
from services.receiving_service import get_remaining_qty


@role_required(Role.WAREHOUSE)
def gr_list(request):
    """Daftar GR + daftar PO siap diterima."""
    from django.core.paginator import Paginator

    pos_ready = PurchaseOrder.objects.filter(
        status__in=[POStatus.SENT, POStatus.PARTIALLY_RECEIVED]
    ).select_related("vendor")
    grs = GoodsReceipt.objects.select_related("po__vendor", "received_by")
    page = Paginator(grs, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "receiving/gr_list.html",
        {
            "pos_ready": pos_ready,
            "grs": page,
            "page_obj": page,
        },
    )


@role_required(Role.WAREHOUSE)
def gr_create(request, po_pk: int):
    """FR-050: Warehouse Receiver buat GR untuk PO SENT/PARTIALLY_RECEIVED."""
    po = get_object_or_404(
        PurchaseOrder.objects.select_related("vendor"),
        pk=po_pk,
        status__in=[POStatus.SENT, POStatus.PARTIALLY_RECEIVED],
    )
    po_items = po.items.select_related("item").all()
    # Sisa qty per item (FR-051)
    po_items_with_remaining = []
    for pi in po_items:
        remaining = get_remaining_qty(pi)
        po_items_with_remaining.append(
            {
                "po_item": pi,
                "remaining": remaining,
                "received": pi.qty - remaining,
            }
        )

    if request.method == "POST":
        try:
            delivery_note_no = request.POST.get("delivery_note_no", "").strip()
            if not delivery_note_no:
                raise BusinessRuleViolation("Nomor surat jalan wajib diisi.")
            received_date = _parse_date(request.POST.get("received_date"))

            items = []
            for pi in po_items:
                qty_str = request.POST.get(f"qty_{pi.pk}", "")
                condition = request.POST.get(f"condition_{pi.pk}", Condition.OK)
                note = request.POST.get(f"note_{pi.pk}", "")
                if qty_str and Decimal(qty_str) > 0:
                    items.append(
                        {
                            "po_item": pi,
                            "qty_received": Decimal(qty_str),
                            "condition": condition,
                            "notes": note,
                        }
                    )

            notes = request.POST.get("notes", "")
            gr = receiving_service.create_gr(
                po=po,
                receiver=request.user,
                delivery_note_no=delivery_note_no,
                received_date=received_date,
                items=items,
                notes=notes,
            )
            messages.success(request, f"GR {gr.number} berhasil dicatat.")
            return redirect("gr_detail", pk=gr.pk)
        except (BusinessRuleViolation, ValueError, ArithmeticError) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "receiving/gr_form.html",
        {
            "po": po,
            "po_items_with_remaining": po_items_with_remaining,
            "condition_choices": Condition.choices,
            "today": datetime.date.today(),
        },
    )


@role_required(Role.WAREHOUSE, Role.OFFICER, Role.MANAGER)
def gr_detail(request, pk: int):
    """Detail GR."""
    gr = get_object_or_404(GoodsReceipt.objects.select_related("po__vendor", "received_by"), pk=pk)
    gr_items = gr.items.select_related("po_item__item")
    return render(
        request,
        "receiving/gr_detail.html",
        {
            "gr": gr,
            "gr_items": gr_items,
        },
    )


def _parse_date(value: str | None) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value or "")
    except (TypeError, ValueError):
        raise BusinessRuleViolation("Tanggal terima tidak valid.") from None
