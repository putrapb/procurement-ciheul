"""URL patterns: requisitions + dashboard. F-03/04/05."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("pr/", views.pr_list, name="pr_list"),
    path("pr/new/", views.pr_create, name="pr_create"),
    path("pr/<int:pk>/", views.pr_detail, name="pr_detail"),
    path("pr/<int:pk>/edit/", views.pr_edit, name="pr_edit"),
    path("pr/<int:pk>/delete/", views.pr_delete, name="pr_delete"),
    path("pr/<int:pk>/submit/", views.pr_submit, name="pr_submit"),
    path("pr/<int:pk>/approve/", views.pr_approve, name="pr_approve"),
    path("pr/<int:pk>/reject/", views.pr_reject, name="pr_reject"),
    path("pr/<int:pk>/revise/", views.pr_revise, name="pr_revise"),
    path("pr/<int:pk>/cancel/", views.pr_cancel, name="pr_cancel"),
]
