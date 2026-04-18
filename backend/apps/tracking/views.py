from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import JobClickEventCreateSerializer, UserSearchEventCreateSerializer
from .services.events import record_click_event, record_search_event


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
