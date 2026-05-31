from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views import View
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.jobs.models import JobPosting
from apps.jobs.services.job_urls import resolve_external_job_url

from .serializers import JobClickEventCreateSerializer, UserSearchEventCreateSerializer
from .services.events import record_click_event, record_search_event
from .services.redirect_pages import render_job_redirect_page


class TrackSearchEventAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserSearchEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = record_search_event(
            user=request.user,
            query=serializer.validated_data["query"],
            filters=serializer.validated_data.get("filters", {}),
            result_count=serializer.validated_data.get("result_count", 0),
            response_ms=serializer.validated_data.get("response_ms"),
        )
        return Response({"id": event.id}, status=status.HTTP_201_CREATED)


class TrackClickEventAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = JobClickEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = record_click_event(
            user=request.user,
            job_id=serializer.validated_data["job_id"],
            search_event_id=serializer.validated_data.get("search_event_id"),
            rank_position=serializer.validated_data.get("rank_position"),
            keyword_score=serializer.validated_data.get("keyword_score"),
            semantic_score=serializer.validated_data.get("semantic_score"),
            final_score=serializer.validated_data.get("final_score"),
        )
        return Response({"id": event.id}, status=status.HTTP_201_CREATED)


class AlertJobClickRedirectView(View):
    """Track alert email job clicks, then open the original listing URL."""

    def get(self, request, job_id: int):
        job = get_object_or_404(JobPosting, pk=job_id)
        try:
            record_click_event(
                user=request.user,
                job_id=job.id,
                rank_position=0,
            )
        except Exception:
            pass

        site_url = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
        search_url = f"{site_url}/search/"
        target = resolve_external_job_url(job.job_url)
        return render_job_redirect_page(target_url=target, search_url=search_url)
