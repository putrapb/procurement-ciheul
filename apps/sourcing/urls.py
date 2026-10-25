"""URL patterns: sourcing. F-06/07/08."""

from django.urls import path

from . import views

urlpatterns = [
    path("rfq/", views.rfq_list, name="rfq_list"),
    path("rfq/new/<int:pr_pk>/", views.rfq_create, name="rfq_create"),
    path("rfq/<int:pk>/", views.rfq_detail, name="rfq_detail"),
    path("rfq/<int:pk>/send/", views.rfq_send, name="rfq_send"),
    path("rfq/<int:pk>/close/", views.rfq_close, name="rfq_close"),
    path("rfq/<int:pk>/quotation/<int:vendor_pk>/", views.quotation_input, name="quotation_input"),
    path("rfq/<int:pk>/compare/", views.quotation_compare, name="quotation_compare"),
    path("quotation/<int:pk>/select/", views.quotation_select, name="quotation_select"),
    path("quotation/<int:pk>/approve/", views.quotation_approve, name="quotation_approve"),
    path("quotation/<int:pk>/reject/", views.quotation_reject, name="quotation_reject"),
]
