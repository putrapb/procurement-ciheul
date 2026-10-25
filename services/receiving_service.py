"""
Receiving service — logika bisnis Goods Receipt (F-11).

FR yang tercakup:
  FR-050  Warehouse Receiver buat GR terhadap PO berstatus SENT/PARTIALLY_RECEIVED
  FR-051  qty diterima tidak boleh melebihi sisa qty PO per item (select_for_update)
  FR-052  Jika semua item terpenuhi → PO + PR COMPLETED; sebagian → PARTIALLY_RECEIVED
  FR-053  Sistem tidak mengelola stok/lokasi gudang

BR yang tercakup:
  BR-05  GR tidak boleh melebihi sisa qty PO
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.accounts.models import Role, User
from apps.core.exceptions import BusinessRuleViolation
from apps.orders.models import POItem, POStatus, PurchaseOrder
from apps.receiving.models import Condition, GoodsReceipt, GRItem
from services.numbering import next_number
from services.state_machine import transition


def _check_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise BusinessRuleViolation(
            f"Aksi ini memerlukan role {'/'.join(roles)}, bukan {user.role}."
        )


def get_remaining_qty(po_item: POItem) -> Decimal:
    """
    Hitung sisa qty PO item yang belum diterima.
    = qty PO - sum(qty_received dari semua GRItem untuk po_item ini)
    """
    from django.db.models import Sum

    received = po_item.gr_items.aggregate(total=Sum("qty_received"))["total"] or Decimal("0")
    return po_item.qty - received


def create_gr(
    po: PurchaseOrder,
    receiver: User,
    delivery_note_no: str,
    received_date: datetime.date,
    items: list[dict[str, Any]],
    notes: str = "",
) -> GoodsReceipt:
    """
    Buat GR untuk PO berstatus SENT atau PARTIALLY_RECEIVED. FR-050/FR-051/FR-052 / BR-05.

    `items` = [{"po_item": POItem, "qty_received": Decimal, "condition": str, "notes": str}, ...]

    Operasi dilakukan dalam satu transaksi atomik dengan select_for_update pada POItem
    untuk mencegah race condition (gate L024).
    """
    _check_role(receiver, Role.WAREHOUSE)
    if po.status not in (POStatus.SENT, POStatus.PARTIALLY_RECEIVED):
        raise BusinessRuleViolation(
            "GR hanya dapat dibuat untuk PO berstatus SENT atau PARTIALLY_RECEIVED."
        )
    if not items:
        raise BusinessRuleViolation("GR harus memiliki minimal 1 item.")
    po_item_ids = [entry["po_item"].pk for entry in items]
    if len(set(po_item_ids)) != len(po_item_ids):
        raise BusinessRuleViolation("Item PO tidak boleh duplikat dalam satu GR.")

    with transaction.atomic():
        # Kunci POItem untuk menghindari race condition (FR-051)
        locked_items = {
            pi.pk: pi for pi in POItem.objects.select_for_update().filter(pk__in=po_item_ids, po=po)
        }
        if len(locked_items) != len(po_item_ids):
            raise BusinessRuleViolation("Item GR tidak berasal dari PO yang dipilih.")

        # Validasi sisa qty sebelum membuat GR (BR-05)
        for entry in items:
            po_item = locked_items[entry["po_item"].pk]
            try:
                qty_recv = Decimal(str(entry["qty_received"]))
            except (ArithmeticError, TypeError, ValueError):
                raise BusinessRuleViolation(
                    f"Qty diterima untuk item {po_item.item.code} tidak valid."
                ) from None
            condition = entry.get("condition", Condition.OK)
            if condition not in Condition.values:
                raise BusinessRuleViolation(
                    f"Kondisi barang untuk item {po_item.item.code} tidak valid."
                )
            if qty_recv <= 0:
                raise BusinessRuleViolation(
                    f"Qty diterima untuk item {po_item.item.code} harus > 0."
                )
            remaining = get_remaining_qty(po_item)
            if qty_recv > remaining:
                raise BusinessRuleViolation(
                    f"Qty diterima ({qty_recv}) melebihi sisa qty PO ({remaining}) "
                    f"untuk item {po_item.item.code} (BR-05)."
                )
            entry["qty_received"] = qty_recv

        number = next_number("GR")
        gr = GoodsReceipt.objects.create(
            number=number,
            po=po,
            delivery_note_no=delivery_note_no,
            received_date=received_date,
            received_by=receiver,
            notes=notes,
        )
        for entry in items:
            po_item = locked_items[entry["po_item"].pk]
            GRItem.objects.create(
                gr=gr,
                po_item=po_item,
                qty_received=entry["qty_received"],
                condition=entry.get("condition", "OK"),
                notes=entry.get("notes", ""),
            )

        # FR-052: Tentukan status PO setelah GR
        _update_po_status_after_gr(po, receiver)

    return gr


def _update_po_status_after_gr(po: PurchaseOrder, user: User) -> None:
    """
    Perbarui status PO (dan PR) setelah GR dibuat.
    Jika semua item PO terpenuhi → COMPLETED; sebagian → PARTIALLY_RECEIVED. FR-052.
    """
    all_fulfilled = True
    for po_item in po.items.all():
        if get_remaining_qty(po_item) > 0:
            all_fulfilled = False
            break

    if all_fulfilled:
        new_po_status = POStatus.COMPLETED
        note_po = "Semua item PO diterima — PO selesai"
    else:
        new_po_status = POStatus.PARTIALLY_RECEIVED
        note_po = "Sebagian item PO diterima"

    if po.status != new_po_status:
        transition(po, new_po_status, user, note_po)

    # Update status PR terkait
    pr = po.quotation.rfq_vendor.rfq.pr
    from apps.requisitions.models import PRStatus

    if all_fulfilled:
        if pr.status in (PRStatus.PO_ISSUED, PRStatus.PARTIALLY_RECEIVED):
            transition(pr, PRStatus.COMPLETED, user, "Semua barang diterima — PR selesai")
    elif pr.status == PRStatus.PO_ISSUED:
        # Penerimaan sebagian pertama: PO_ISSUED → PARTIALLY_RECEIVED.
        transition(pr, PRStatus.PARTIALLY_RECEIVED, user, "Barang diterima sebagian")
