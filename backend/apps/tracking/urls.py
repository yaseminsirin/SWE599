from django.urls import path

from .views import AlertJobClickRedirectView, TrackClickEventAPIView, TrackSearchEventAPIView

urlpatterns = [
    path("tracking/search/", TrackSearchEventAPIView.as_view(), name="track-search"),
    path("tracking/click/", TrackClickEventAPIView.as_view(), name="track-click"),
    path(
        "tracking/alert-click/<int:job_id>/",
        AlertJobClickRedirectView.as_view(),
        name="track-alert-click",
    ),
]
