"""URL patterns: orders. F-09/10/14."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.po_list, name="po_list"),
    path("new/<int:quotation_pk>/", views.po_create, name="po_create"),
    path("<int:pk>/", views.po_detail, name="po_detail"),
    path("<int:pk>/approve/", views.po_approve, name="po_approve"),
    path("<int:pk>/reject/", views.po_reject, name="po_reject"),
    path("<int:pk>/send/", views.po_send, name="po_send"),
    path("<int:pk>/resubmit/", views.po_resubmit, name="po_resubmit"),
    path("<int:pk>/cancel/", views.po_cancel, name="po_cancel"),
    path("<int:pk>/print/", views.po_print, name="po_print"),
]
