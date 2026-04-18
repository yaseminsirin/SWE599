from django.urls import path

from .views import (
    JobDetailAPIView,
    JobListAPIView,
    JobSearchAPIView,
    RankedJobSearchAPIView,
    SemanticJobSearchAPIView,
)

urlpatterns = [
    path("jobs/", JobListAPIView.as_view(), name="job-list"),
    path("jobs/<int:pk>/", JobDetailAPIView.as_view(), name="job-detail"),
    path("jobs/search/", JobSearchAPIView.as_view(), name="job-search"),
    path("jobs/ranked-search/", RankedJobSearchAPIView.as_view(), name="job-ranked-search"),
    path("jobs/semantic-search/", SemanticJobSearchAPIView.as_view(), name="job-semantic-search"),
]
