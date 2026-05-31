from django.urls import path

from .views import AlertDetailAPIView, AlertListCreateAPIView, CancelAllAlertsAPIView

urlpatterns = [
    path("alerts/cancel-all/", CancelAllAlertsAPIView.as_view(), name="alert-cancel-all"),
    path("alerts/", AlertListCreateAPIView.as_view(), name="alert-list-create"),
    path("alerts/<int:pk>/", AlertDetailAPIView.as_view(), name="alert-detail"),
]
