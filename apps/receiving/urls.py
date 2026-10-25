"""URL patterns: receiving. F-11."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.gr_list, name="gr_list"),
    path("new/<int:po_pk>/", views.gr_create, name="gr_create"),
    path("<int:pk>/", views.gr_detail, name="gr_detail"),
]
