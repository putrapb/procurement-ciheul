import datetime

import pytest

from apps.accounts.models import Role, User
from apps.masterdata.models import Department, Item, Vendor
from apps.requisitions.models import PRItem, PurchaseRequest


@pytest.fixture
def dept(db):
    return Department.objects.create(code="IT", name="Information Technology")


@pytest.fixture
def make_user(db, dept):
    def _make(username: str, role: str = Role.REQUESTER):
        return User.objects.create_user(
            username=username, password="pw12345!", role=role, department=dept
        )

    return _make


@pytest.fixture
def item(db):
    return Item.objects.create(code="LPT-01", name="Laptop", uom="unit")


@pytest.fixture
def vendor(db):
    return Vendor.objects.create(code="V-001", name="PT Vendor Satu")


@pytest.fixture
def pr(db, make_user, dept, item):
    requester = make_user("req1")
    pr = PurchaseRequest.objects.create(
        number="PR-TEST-0001",
        requester=requester,
        department=dept,
        needed_date=datetime.date.today() + datetime.timedelta(days=14),
        reason="Penggantian laptop",
    )
    PRItem.objects.create(pr=pr, item=item, qty=5)
    return pr
