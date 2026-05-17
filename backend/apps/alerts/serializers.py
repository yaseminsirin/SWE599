from rest_framework import serializers

from .models import JobAlert


class JobAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobAlert
        fields = [
            "id",
            "name",
            "keyword",
            "location_text",
            "is_remote",
            "employment_type",
            "filters",
            "is_active",
            "notify_email",
            "last_notified_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_notified_at", "created_at", "updated_at"]
