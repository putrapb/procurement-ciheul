"""
Views: sourcing (RFQ + Quotation). F-06/07/08.
Semua view tipis — logika di sourcing_service.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.core.exceptions import BusinessRuleViolation, InvalidTransition
from apps.masterdata.models import Vendor
from apps.requisitions.models import PRStatus, PurchaseRequest
from apps.sourcing.models import RFQ, Quotation, QuotationStatus, RFQVendor
from services import ai_extractor, sourcing_service

# ──────────────────────────────────────────────────────────────────────────────
# RFQ
# ──────────────────────────────────────────────────────────────────────────────


@role_required(Role.OFFICER, Role.MANAGER)
def rfq_list(request):
    """Daftar RFQ."""
    from django.core.paginator import Paginator

    qs = RFQ.objects.select_related("pr").order_by("-created_at")
    search = request.GET.get("q", "")
    if search:
        qs = qs.filter(number__icontains=search)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "sourcing/rfq_list.html",
        {"page_obj": page, "search": search},
    )


@role_required(Role.OFFICER)
def rfq_create(request, pr_pk: int):
    """FR-030: Officer buat RFQ dari PR APPROVED."""
    pr = get_object_or_404(PurchaseRequest, pk=pr_pk, status=PRStatus.APPROVED)
    vendors = Vendor.objects.filter(is_active=True)

    if request.method == "POST":
        try:
            due_date = datetime.date.fromisoformat(request.POST.get("due_date", ""))
            vendor_ids = [int(v) for v in request.POST.getlist("vendor_ids")]
            rfq = sourcing_service.create_rfq(pr, request.user, due_date, vendor_ids)
            messages.success(request, f"RFQ {rfq.number} berhasil dibuat.")
            return redirect("rfq_detail", pk=rfq.pk)
        except (BusinessRuleViolation, ValueError) as exc:
            messages.error(request, str(exc))

    return render(request, "sourcing/rfq_form.html", {"pr": pr, "vendors": vendors})


@role_required(Role.OFFICER, Role.MANAGER)
def rfq_detail(request, pk: int):
    """Detail RFQ + daftar vendor + status quotation."""
    rfq = get_object_or_404(RFQ.objects.select_related("pr", "created_by"), pk=pk)
    rfq_vendors = list(rfq.rfq_vendors.select_related("vendor").prefetch_related("quotation"))
    has_selected = any(
        getattr(rv, "quotation", None) and rv.quotation.status == QuotationStatus.SELECTED
        for rv in rfq_vendors
    )
    return render(
        request,
        "sourcing/rfq_detail.html",
        {
            "rfq": rfq,
            "rfq_vendors": rfq_vendors,
            "has_selected": has_selected,
        },
    )


@role_required(Role.OFFICER)
def rfq_send(request, pk: int):
    """FR-031: Tandai RFQ terkirim."""
    rfq = get_object_or_404(RFQ, pk=pk)
    if request.method == "POST":
        try:
            sourcing_service.send_rfq(rfq, request.user)
            messages.success(request, f"RFQ {rfq.number} ditandai terkirim.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("rfq_detail", pk=pk)


@role_required(Role.OFFICER)
def rfq_close(request, pk: int):
    """Tutup RFQ agar tidak menerima penawaran baru."""
    rfq = get_object_or_404(RFQ, pk=pk)
    if request.method == "POST":
        try:
            sourcing_service.close_rfq(rfq, request.user)
            messages.success(request, f"RFQ {rfq.number} ditutup.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("rfq_detail", pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
# Quotation
# ──────────────────────────────────────────────────────────────────────────────


@role_required(Role.OFFICER)
def quotation_input(request, pk: int, vendor_pk: int):
    """FR-032: Input penawaran per vendor."""
    rfq = get_object_or_404(RFQ, pk=pk)
    rfq_vendor = get_object_or_404(RFQVendor, rfq=rfq, vendor_id=vendor_pk)
    pr_items = rfq.pr.items.select_related("item").all()
    existing = getattr(rfq_vendor, "quotation", None)

    if request.method == "POST":
        if request.POST.get("action") == "extract":
            result = ai_extractor.extract_quotation(request.FILES.get("ai_file"))
            if result.error:
                messages.error(request, result.message)
            else:
                messages.info(request, result.message)
            return render(
                request,
                "sourcing/quotation_form.html",
                {
                    "rfq": rfq,
                    "rfq_vendor": rfq_vendor,
                    "pr_items": pr_items,
                    "existing": existing,
                    "ai_result": result,
                    "ai_prices": _match_ai_prices(result, pr_items),
                },
            )

        try:
            lead_time = int(request.POST.get("lead_time_days", 0) or 0)
            valid_until_str = request.POST.get("valid_until", "")
            valid_until = datetime.date.fromisoformat(valid_until_str) if valid_until_str else None
            terms = request.POST.get("terms", "")

            items = []
            for pri in pr_items:
                price_str = request.POST.get(f"price_{pri.pk}", "")
                if price_str:
                    items.append({"pr_item": pri, "unit_price": Decimal(price_str)})

            sourcing_service.submit_quotation(
                rfq_vendor,
                request.user,
                lead_time_days=lead_time,
                valid_until=valid_until,
                terms=terms,
                items=items,
                attachment=request.FILES.get("attachment"),
            )
            messages.success(request, "Penawaran berhasil disimpan.")
            return redirect("rfq_detail", pk=pk)
        except (BusinessRuleViolation, ValueError, ArithmeticError) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "sourcing/quotation_form.html",
        {
            "rfq": rfq,
            "rfq_vendor": rfq_vendor,
            "pr_items": pr_items,
            "existing": existing,
        },
    )


@role_required(Role.OFFICER, Role.MANAGER)
def quotation_compare(request, pk: int):
    """FR-033: Tabel perbandingan penawaran."""
    rfq = get_object_or_404(RFQ, pk=pk)
    comparison = sourcing_service.get_comparison_data(rfq)
    return render(request, "sourcing/quotation_compare.html", comparison)


@role_required(Role.OFFICER)
def quotation_select(request, pk: int):
    """FR-034: Officer pilih satu Quotation sebagai pemenang."""
    quotation = get_object_or_404(Quotation, pk=pk)
    rfq = quotation.rfq_vendor.rfq

    if request.method == "POST":
        justification = request.POST.get("justification", "")
        try:
            comparison = sourcing_service.get_comparison_data(rfq)
            sourcing_service.select_quotation(quotation, request.user, justification, comparison)
            messages.success(request, "Vendor berhasil dipilih, menunggu approval Manager.")
            return redirect("rfq_detail", pk=rfq.pk)
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "sourcing/quotation_select.html",
        {
            "quotation": quotation,
            "rfq": rfq,
        },
    )


@role_required(Role.MANAGER)
def quotation_approve(request, pk: int):
    """FR-035: Manager setujui pemilihan vendor."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == "POST":
        note = request.POST.get("note", "")
        try:
            sourcing_service.approve_vendor_selection(quotation, request.user, note)
            messages.success(request, "Pemilihan vendor disetujui.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("rfq_detail", pk=quotation.rfq_vendor.rfq.pk)


@role_required(Role.MANAGER)
def quotation_reject(request, pk: int):
    """Manager tolak pemilihan vendor."""
    quotation = get_object_or_404(Quotation, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "")
        try:
            sourcing_service.reject_vendor_selection(quotation, request.user, reason)
            messages.success(request, "Pemilihan vendor ditolak.")
        except (BusinessRuleViolation, InvalidTransition) as exc:
            messages.error(request, str(exc))
    return redirect("rfq_detail", pk=quotation.rfq_vendor.rfq.pk)


def _match_ai_prices(result, pr_items) -> dict:
    """Petakan hasil ekstraksi AI ke PRItem berdasarkan nama/kode item."""
    prices: dict[int, Decimal] = {}
    for extracted in result.items:
        if extracted.unit_price is None:
            continue
        name = (extracted.item_name or "").strip().lower()
        for pri in pr_items:
            if name in (pri.item.name.strip().lower(), pri.item.code.strip().lower()):
                prices[pri.pk] = extracted.unit_price
    return prices
