#!/usr/bin/env python
"""
scripts/seed_data.py — Buat akun demo + data master contoh (idempoten).

Jalankan: python scripts/seed_data.py
Aman dijalankan berkali-kali — data yang sudah ada tidak akan digandakan.

Akun demo (hanya untuk evaluasi lokal):
  admin     / admin123   → Admin
  requester / demo123    → Requester
  depthead  / demo123    → Dept Head
  officer   / demo123    → Procurement Officer
  manager   / demo123    → Procurement Manager
  warehouse / demo123    → Warehouse Receiver
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Setup Django sebelum import model
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from apps.accounts.models import Role  # noqa: E402
from apps.masterdata.models import Department, Item, Vendor  # noqa: E402

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _created(created: bool, label: str) -> str:
    return f"  {'✓ BARU' if created else '– sudah ada':12s} {label}"


# ──────────────────────────────────────────────────────────────────────────────
# Departemen
# ──────────────────────────────────────────────────────────────────────────────


def seed_departments() -> dict:
    print("\n[Departemen]")
    depts = {}
    data = [
        ("IT", "Information Technology"),
        ("HR", "Human Resources"),
        ("OPS", "Operations"),
        ("FIN", "Finance"),
        ("MKT", "Marketing"),
    ]
    for code, name in data:
        d, created = Department.objects.get_or_create(code=code, defaults={"name": name})
        depts[code] = d
        print(_created(created, f"{code} – {name}"))
    return depts


# ──────────────────────────────────────────────────────────────────────────────
# Item
# ──────────────────────────────────────────────────────────────────────────────


def seed_items() -> dict:
    print("\n[Item]")
    items = {}
    data = [
        ("LPT-001", "Laptop Standar 14 inci", "unit"),
        ("MON-001", "Monitor 24 inci FHD", "unit"),
        ("MOU-001", "Mouse Wireless", "unit"),
        ("KBD-001", "Keyboard Mechanical", "unit"),
        ("PRN-001", "Printer Laser A4", "unit"),
        ("ATK-001", "Kertas HVS A4 80gr", "rim"),
        ("ATK-002", "Pulpen Ballpoint (12pcs/box)", "box"),
        ("DSK-001", "Meja Kerja Minimalis", "unit"),
        ("CHR-001", "Kursi Ergonomis", "unit"),
        ("CAB-001", "Lemari Arsip 2 Pintu", "unit"),
    ]
    for code, name, uom in data:
        it, created = Item.objects.get_or_create(code=code, defaults={"name": name, "uom": uom})
        items[code] = it
        print(_created(created, f"{code} – {name}"))
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Vendor
# ──────────────────────────────────────────────────────────────────────────────


def seed_vendors() -> dict:
    print("\n[Vendor]")
    vendors = {}
    data = [
        ("VND-001", "PT Teknologi Maju", "Budi Santoso", "budi@teknomaju.co.id", "021-5551234"),
        ("VND-002", "CV Sumber Jaya", "Ani Rahayu", "ani@sumberjaya.com", "021-5552345"),
        ("VND-003", "PT Prima Solusi", "Dedi Kurniawan", "dedi@primasolusi.id", "021-5553456"),
    ]
    for code, name, contact, email, phone in data:
        v, created = Vendor.objects.get_or_create(
            code=code,
            defaults={"name": name, "contact_person": contact, "email": email, "phone": phone},
        )
        vendors[code] = v
        print(_created(created, f"{code} – {name}"))
    return vendors


# ──────────────────────────────────────────────────────────────────────────────
# User
# ──────────────────────────────────────────────────────────────────────────────


def seed_users(depts: dict) -> dict:
    print("\n[User Demo]")
    users = {}
    data = [
        ("admin", "admin123", Role.ADMIN, None, True, True, "Admin", "Sistem"),
        ("requester", "demo123", Role.REQUESTER, "IT", False, False, "Ahmad", "Requester"),
        ("depthead", "demo123", Role.DEPT_HEAD, "IT", False, False, "Budi", "DeptHead"),
        ("officer", "demo123", Role.OFFICER, None, False, False, "Citra", "Officer"),
        ("manager", "demo123", Role.MANAGER, None, False, False, "Dian", "Manager"),
        ("warehouse", "demo123", Role.WAREHOUSE, None, False, False, "Eko", "Warehouse"),
    ]
    for username, password, role, dept_code, is_staff, is_super, fname, lname in data:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "role": role,
                "department": depts.get(dept_code) if dept_code else None,
                "is_staff": is_staff,
                "is_superuser": is_super,
                "first_name": fname,
                "last_name": lname,
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        users[username] = user
        print(_created(created, f"{username:12s} [{role}]"))
    return users


# ──────────────────────────────────────────────────────────────────────────────
# Contoh PR
# ──────────────────────────────────────────────────────────────────────────────


def seed_sample_pr(users: dict, depts: dict, items: dict) -> None:
    print("\n[Contoh PR]")
    from apps.requisitions.models import PurchaseRequest

    if PurchaseRequest.objects.filter(number__startswith="PR-DEMO").exists():
        print("  – sudah ada, dilewati")
        return

    import datetime

    from services import requisition_service

    pr = requisition_service.create_pr(
        requester=users["requester"],
        department=depts["IT"],
        needed_date=datetime.date.today() + datetime.timedelta(days=14),
        reason="Penggantian laptop IT staff yang sudah 5 tahun",
        items=[
            {"item": items["LPT-001"], "qty": 3, "notes": "Spec minimal i5 Gen 12"},
            {"item": items["MON-001"], "qty": 3, "notes": ""},
        ],
    )
    # Override nomor agar mudah dikenali (hanya untuk seed demo)
    PurchaseRequest.objects.filter(pk=pr.pk).update(number="PR-DEMO-0001")
    pr.refresh_from_db()
    print(f"  ✓ BARU   {pr.number}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 50)
    print("  seed_data.py — Data Demo Procurement Ciheul")
    print("=" * 50)

    depts = seed_departments()
    items = seed_items()
    seed_vendors()
    users = seed_users(depts)
    seed_sample_pr(users, depts, items)

    print("\n" + "=" * 50)
    print("  Selesai! Akun demo:")
    print("  admin      / admin123  (Admin + akses /admin/)")
    print("  requester  / demo123   (Requester)")
    print("  depthead   / demo123   (Dept Head)")
    print("  officer    / demo123   (Procurement Officer)")
    print("  manager    / demo123   (Procurement Manager)")
    print("  warehouse  / demo123   (Warehouse Receiver)")
    print("=" * 50)
    print("  ⚠️  Jangan gunakan di production!")
    print("=" * 50)


if __name__ == "__main__":
    main()
