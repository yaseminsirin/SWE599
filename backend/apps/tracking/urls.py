from django.urls import path

from .views import TrackClickEventAPIView, TrackSearchEventAPIView

urlpatterns = [
    path("tracking/search/", TrackSearchEventAPIView.as_view(), name="track-search"),
    path("tracking/click/", TrackClickEventAPIView.as_view(), name="track-click"),
]
