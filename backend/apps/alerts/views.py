from rest_framework import generics, permissions

from .models import JobAlert
from .serializers import JobAlertSerializer


class AlertListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = JobAlertSerializer
    permission_classes = [permissions.AllowAny]
    queryset = JobAlert.objects.all().order_by("-created_at")


class AlertDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = JobAlertSerializer
    permission_classes = [permissions.AllowAny]
    queryset = JobAlert.objects.all()
