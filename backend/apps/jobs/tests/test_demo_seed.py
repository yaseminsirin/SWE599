from django.test import TestCase

from apps.jobs.models import JobPosting, RawJobRecord
from apps.jobs.services.demo_dataset import DEMO_SOURCE, iter_demo_job_dicts
from apps.jobs.services.demo_seed import clear_demo_jobs, seed_demo_jobs


class DemoSeedTests(TestCase):
    def test_demo_dataset_size_and_categories(self):
        jobs = iter_demo_job_dicts()
        self.assertGreaterEqual(len(jobs), 40)
        self.assertLessEqual(len(jobs), 60)
        categories = {j["category_normalized"] for j in jobs}
        self.assertIn("Python Backend Developer", categories)
        self.assertIn("Machine Learning Engineer", categories)
        self.assertIn("Business Analyst", categories)

    def test_seed_and_reset_demo_jobs(self):
        first = seed_demo_jobs(reset=True)
        self.assertGreaterEqual(first["demo_jobs_total"], 40)
        self.assertEqual(
            JobPosting.objects.filter(source=DEMO_SOURCE).count(),
            first["demo_jobs_total"],
        )
        self.assertTrue(RawJobRecord.objects.filter(source=DEMO_SOURCE).exists())

        cleared = clear_demo_jobs()
        self.assertGreater(cleared["job_postings_deleted"], 0)
        self.assertEqual(JobPosting.objects.filter(source=DEMO_SOURCE).count(), 0)

        second = seed_demo_jobs(reset=True)
        self.assertEqual(second["demo_jobs_total"], first["demo_jobs_total"])
