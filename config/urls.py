"""URL configuration. F-01 (auth) + F-02 to F-11."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("apps.requisitions.urls")),
    path("approvals/", include("apps.approvals.urls")),
    path("sourcing/", include("apps.sourcing.urls")),
    path("orders/", include("apps.orders.urls")),
    path("receiving/", include("apps.receiving.urls")),
    path("masterdata/", include("apps.masterdata.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
