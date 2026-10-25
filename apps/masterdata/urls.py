"""URL patterns: masterdata. F-02."""

from django.urls import path

from . import views

urlpatterns = [
    path("departments/", views.department_list, name="department_list"),
    path("items/", views.item_list, name="item_list"),
    path("vendors/", views.vendor_list, name="vendor_list"),
]
