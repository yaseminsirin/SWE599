from rest_framework import serializers


class UserSearchEventCreateSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=255)
    filters = serializers.JSONField(required=False, default=dict)
    result_count = serializers.IntegerField(required=False, default=0, min_value=0)
    response_ms = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class JobClickEventCreateSerializer(serializers.Serializer):
    job_id = serializers.IntegerField()
    search_event_id = serializers.IntegerField(required=False, allow_null=True)
    rank_position = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    keyword_score = serializers.FloatField(required=False, allow_null=True)
    semantic_score = serializers.FloatField(required=False, allow_null=True)
    final_score = serializers.FloatField(required=False, allow_null=True)
