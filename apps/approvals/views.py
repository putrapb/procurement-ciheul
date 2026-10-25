"""Views: approvals queue."""

from __future__ import annotations

from django.shortcuts import render

from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.approvals.models import Approval, ApprovalStatus


@role_required(Role.DEPT_HEAD, Role.MANAGER)
def approval_queue(request):
    """Antrean approval untuk Dept Head dan Manager."""
    pending = Approval.objects.filter(
        status=ApprovalStatus.PENDING,
        required_role=request.user.role,
    ).select_related("content_type")

    if request.user.role == Role.DEPT_HEAD:
        from django.contrib.contenttypes.models import ContentType

        from apps.requisitions.models import PurchaseRequest

        ct = ContentType.objects.get_for_model(PurchaseRequest)
        pr_ids = PurchaseRequest.objects.filter(department=request.user.department).values_list(
            "pk", flat=True
        )
        pending = pending.filter(content_type=ct, object_id__in=pr_ids)

    return render(request, "approvals/queue.html", {"pending": pending})
