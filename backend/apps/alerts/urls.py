from django.urls import path

from .views import AlertDetailAPIView, AlertListCreateAPIView

urlpatterns = [
    path("alerts/", AlertListCreateAPIView.as_view(), name="alert-list-create"),
    path("alerts/<int:pk>/", AlertDetailAPIView.as_view(), name="alert-detail"),
]
