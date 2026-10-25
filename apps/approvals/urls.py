"""URL patterns: approvals. Used for the approval queue view."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.approval_queue, name="approval_queue"),
]
