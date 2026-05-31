from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import JobAlert
from .serializers import JobAlertSerializer


class CancelAllAlertsSerializer(serializers.Serializer):
    notify_email = serializers.EmailField()

    def validate_notify_email(self, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise serializers.ValidationError("Email is required.")
        return cleaned


class AlertListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = JobAlertSerializer
    permission_classes = [permissions.AllowAny]
    queryset = JobAlert.objects.all().order_by("-created_at")


class AlertDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JobAlertSerializer
    permission_classes = [permissions.AllowAny]
    queryset = JobAlert.objects.all()


class CancelAllAlertsAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = CancelAllAlertsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["notify_email"]
        qs = JobAlert.objects.filter(notify_email__iexact=email)
        cancelled_count = qs.count()
        qs.delete()
        return Response(
            {
                "cancelled_count": cancelled_count,
                "detail": (
                    f"Cancelled {cancelled_count} alert(s) for {email}."
                    if cancelled_count
                    else f"No alerts were found for {email}."
                ),
            },
            status=status.HTTP_200_OK,
        )
