from rest_framework import serializers

from apps.jobs.models import JobPosting


class JobPostingSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPosting
        fields = [
            "id",
            "title",
            "company_name",
            "location_text",
            "city",
            "country",
            "is_remote",
            "employment_type",
            "job_url",
            "posted_at",
            "salary_min",
            "salary_max",
            "salary_currency",
            "category_normalized",
        ]


class JobPostingDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPosting
        fields = [
            "id",
            "source",
            "source_job_id",
            "title",
            "normalized_title",
            "company_name",
            "description_clean",
            "job_url",
            "location_text",
            "city",
            "country",
            "is_remote",
            "employment_type",
            "posted_at",
            "expires_at",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "category_normalized",
            "created_at",
            "updated_at",
        ]
