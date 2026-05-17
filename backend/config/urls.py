from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from .views import alerts_view, home_view, search_view

urlpatterns = [
    path("", home_view, name="ui-home"),
    path("login/", RedirectView.as_view(url="/search/", permanent=False), name="ui-login-redirect"),
    path("search/", search_view, name="ui-search"),
    path("alerts/", alerts_view, name="ui-alerts"),
    path("admin/", admin.site.urls),
    path("api/", include("apps.search.urls")),
    path("api/", include("apps.alerts.urls")),
    path("api/", include("apps.tracking.urls")),
]
