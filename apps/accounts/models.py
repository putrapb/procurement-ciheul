from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    REQUESTER = "REQUESTER", "Requester"
    DEPT_HEAD = "DEPT_HEAD", "Dept Head"
    OFFICER = "OFFICER", "Procurement Officer"
    MANAGER = "MANAGER", "Procurement Manager"
    WAREHOUSE = "WAREHOUSE", "Warehouse Receiver"


class User(AbstractUser):
    """Satu user = satu role. Dept Head ditentukan oleh role DEPT_HEAD + department."""

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.REQUESTER)
    department = models.ForeignKey(
        "masterdata.Department",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
    )

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.username} ({self.role})"
