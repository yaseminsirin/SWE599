from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.search.urls")),
    path("api/", include("apps.alerts.urls")),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.tracking.urls")),
]
