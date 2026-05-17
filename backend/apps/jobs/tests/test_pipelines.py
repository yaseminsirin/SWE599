from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.jobs.models import JobPosting, RawJobRecord
from apps.jobs.services.ingestion_pipeline import (
    ingest_source,
    prune_stale_jobs,
    save_raw_record,
    upsert_raw_record,
)
from apps.jobs.services.normalization_pipeline import normalize_raw_records_batch


class JobsPipelineTests(TestCase):
    def test_save_raw_record_skips_exact_duplicate(self):
        raw = {
            "source": "adzuna",
            "source_job_id": "job-1",
            "payload": {"id": "job-1", "title": "Backend Engineer"},
            "fetched_at": timezone.now(),
        }
        self.assertTrue(save_raw_record(raw))
        self.assertFalse(save_raw_record(raw))
        self.assertEqual(RawJobRecord.objects.count(), 1)

    def test_upsert_raw_record_updates_payload_and_resets_processed(self):
        raw = {
            "source": "adzuna",
            "source_job_id": "job-1",
            "payload": {"id": "job-1", "title": "Backend Engineer"},
            "fetched_at": timezone.now(),
        }
        created, updated = upsert_raw_record(raw)
        self.assertTrue(created)
        self.assertFalse(updated)

        record = RawJobRecord.objects.get(source="adzuna", source_job_id="job-1")
        record.processed_at = timezone.now()
        record.save(update_fields=["processed_at"])

        created2, updated2 = upsert_raw_record(
            {
                **raw,
                "payload": {"id": "job-1", "title": "Senior Backend Engineer"},
            }
        )
        self.assertFalse(created2)
        self.assertTrue(updated2)
        record.refresh_from_db()
        self.assertIsNone(record.processed_at)
        self.assertEqual(RawJobRecord.objects.count(), 1)

    def test_prune_stale_jobs_removes_missing_postings_and_raw(self):
        posting = JobPosting.objects.create(
            source="adzuna",
            source_job_id="gone",
            title="Old",
            job_url="https://example.com/old",
            content_hash="hash-gone",
        )
        RawJobRecord.objects.create(
            source="adzuna",
            source_job_id="gone",
            payload={"id": "gone"},
        )
        RawJobRecord.objects.create(
            source="adzuna",
            source_job_id="keep",
            payload={"id": "keep"},
        )
        JobPosting.objects.create(
            source="adzuna",
            source_job_id="keep",
            title="Keep",
            job_url="https://example.com/keep",
            content_hash="hash-keep",
        )

        result = prune_stale_jobs("adzuna", {"keep"})
        self.assertEqual(result["deleted_postings"], 1)
        self.assertEqual(result["deleted_raw_records"], 1)
        self.assertFalse(JobPosting.objects.filter(source_job_id="gone").exists())
        self.assertTrue(JobPosting.objects.filter(source_job_id="keep").exists())

    @patch("apps.jobs.services.ingestion_pipeline.ADAPTERS")
    def test_ingest_source_returns_summary_and_stores_records(self, mock_adapters):
        class DummyAdapter:
            def fetch_jobs(self, *, page, per_page):
                if page > 1:
                    return []
                return [
                    {
                        "source": "adzuna",
                        "source_job_id": "j-1",
                        "payload": {"id": "j-1"},
                        "fetched_at": timezone.now(),
                    },
                    {
                        "source": "adzuna",
                        "source_job_id": "j-2",
                        "payload": {"id": "j-2"},
                        "fetched_at": timezone.now(),
                    },
                ]

        mock_adapters.get.return_value = DummyAdapter
        result = ingest_source("adzuna", sync=False)
        self.assertEqual(result["source"], "adzuna")
        self.assertEqual(result["fetched_records"], 2)
        self.assertEqual(result["created_records"], 2)
        self.assertEqual(RawJobRecord.objects.count(), 2)

    @patch("apps.jobs.services.ingestion_pipeline.prune_stale_jobs")
    @patch("apps.jobs.services.ingestion_pipeline.ADAPTERS")
    def test_ingest_source_sync_prunes_stale_ids(self, mock_adapters, mock_prune):
        class DummyAdapter:
            def fetch_jobs(self, *, page, per_page):
                if page > 1:
                    return []
                return [
                    {
                        "source": "adzuna",
                        "source_job_id": "active-1",
                        "payload": {"id": "active-1"},
                        "fetched_at": timezone.now(),
                    },
                ]

        mock_adapters.get.return_value = DummyAdapter
        mock_prune.return_value = {"deleted_postings": 0, "deleted_raw_records": 0}

        result = ingest_source("adzuna", sync=True)
        mock_prune.assert_called_once()
        self.assertEqual(mock_prune.call_args[0][1], {"active-1"})
        self.assertEqual(result["active_source_job_ids"], ["active-1"])

    def test_normalization_creates_updates_and_dedupes(self):
        payload = {
            "id": "same-id",
            "title": "Python Engineer",
            "description": "Build APIs",
            "redirect_url": "https://example.com/job/1",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "New York, US", "area": ["US", "New York"]},
            "category": {"label": "Software"},
            "contract_type": "full_time",
        }
        raw1 = RawJobRecord.objects.create(
            source="adzuna",
            source_job_id="same-id",
            payload=payload,
        )
        summary1 = normalize_raw_records_batch(batch_size=10)
        self.assertEqual(summary1["normalized_created"], 1)
        posting = JobPosting.objects.get(source="adzuna", source_job_id="same-id")
        raw1.refresh_from_db()
        self.assertIsNotNone(raw1.processed_at)
        self.assertEqual(raw1.normalized_job_id, posting.id)

        payload_updated = {**payload, "description": "Build APIs and pipelines"}
        raw2 = RawJobRecord.objects.create(
            source="adzuna",
            source_job_id="same-id",
            payload=payload_updated,
        )
        summary2 = normalize_raw_records_batch(batch_size=10)
        self.assertEqual(summary2["normalized_updated"], 1)
        posting.refresh_from_db()
        raw2.refresh_from_db()
        self.assertIn("pipelines", posting.description_clean)
        self.assertEqual(raw2.normalized_job_id, posting.id)

        remotive_payload = {
            "id": 999,
            "title": "Python Engineer",
            "description": "Build APIs and pipelines",
            "url": "https://another.example/job/999",
            "company_name": "Acme",
            "candidate_required_location": "New York, US",
            "job_type": "full_time",
            "category": "Software",
        }
        raw3 = RawJobRecord.objects.create(
            source="remotive",
            source_job_id="999",
            payload=remotive_payload,
        )
        summary3 = normalize_raw_records_batch(batch_size=10)
        self.assertEqual(summary3["duplicates_merged_skipped"], 1)
        raw3.refresh_from_db()
        self.assertEqual(raw3.normalized_job_id, posting.id)

    def test_processed_at_remains_null_on_normalization_error(self):
        raw = RawJobRecord.objects.create(
            source="unknown-source",
            source_job_id="bad-1",
            payload={"foo": "bar"},
        )
        summary = normalize_raw_records_batch(batch_size=10)
        self.assertEqual(len(summary["normalization_errors"]), 1)
        raw.refresh_from_db()
        self.assertIsNone(raw.processed_at)
