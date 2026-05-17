from rest_framework import serializers

from apps.jobs.models import JobPosting
from apps.jobs.services.job_labels import (
    category_label_from_raw,
    employment_label_from_raw,
    employment_type_label,
    format_location_display,
    format_salary_display,
    infer_is_remote,
    normalize_employment_slug,
    remote_label,
    source_label,
)


class JobPostingSerializer(serializers.ModelSerializer):
    source = serializers.CharField(read_only=True)
    employment_type_label = serializers.SerializerMethodField()
    is_remote = serializers.SerializerMethodField()
    source_label = serializers.SerializerMethodField()
    location_display = serializers.SerializerMethodField()
    salary_display = serializers.SerializerMethodField()
    remote_label = serializers.SerializerMethodField()
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = JobPosting
        fields = [
            "id",
            "source",
            "source_label",
            "title",
            "company_name",
            "location_text",
            "location_display",
            "city",
            "country",
            "is_remote",
            "remote_label",
            "employment_type",
            "employment_type_label",
            "description_clean",
            "job_url",
            "posted_at",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "salary_display",
            "category_normalized",
            "category_label",
        ]

    def _employment_slug(self, obj: JobPosting) -> str:
        slug = normalize_employment_slug(obj.employment_type)
        if slug:
            return slug
        return normalize_employment_slug(employment_label_from_raw(obj.employment_type))

    def get_employment_type_label(self, obj: JobPosting) -> str:
        slug = self._employment_slug(obj)
        label = employment_type_label(slug)
        if label:
            return label
        return employment_label_from_raw(obj.employment_type)

    def get_is_remote(self, obj: JobPosting) -> bool:
        slug = self._employment_slug(obj)
        return infer_is_remote(
            is_remote=obj.is_remote,
            source=obj.source,
            title=obj.title,
            description=obj.description_clean,
            location=obj.location_text,
            employment_slug=slug,
        )

    def get_source_label(self, obj: JobPosting) -> str:
        return source_label(obj.source)

    def get_location_display(self, obj: JobPosting) -> str:
        remote = self.get_is_remote(obj)
        return format_location_display(
            location_text=obj.location_text,
            city=obj.city,
            country=obj.country,
            is_remote=remote,
        )

    def get_salary_display(self, obj: JobPosting) -> str:
        return format_salary_display(
            salary_min=obj.salary_min,
            salary_max=obj.salary_max,
            salary_currency=obj.salary_currency,
            salary_period=obj.salary_period,
            source=obj.source,
        )

    def get_remote_label(self, obj: JobPosting) -> str:
        return remote_label(is_remote=self.get_is_remote(obj))

    def get_category_label(self, obj: JobPosting) -> str:
        return category_label_from_raw(obj.category_raw) or category_label_from_raw(
            obj.category_normalized
        )


class JobPostingDetailSerializer(JobPostingSerializer):
    class Meta(JobPostingSerializer.Meta):
        fields = JobPostingSerializer.Meta.fields + [
            "source_job_id",
            "normalized_title",
            "expires_at",
            "created_at",
            "updated_at",
        ]
