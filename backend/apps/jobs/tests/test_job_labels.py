from django.test import SimpleTestCase

from apps.jobs.services.job_labels import (
    category_label_from_raw,
    employment_label_from_raw,
    format_salary_display,
    normalize_employment_slug,
)


class JobLabelsTests(SimpleTestCase):
    def test_usajobs_schedule_list(self):
        raw = [{"Code": "6", "Name": "1-Full time and 1-Part time 32 hours"}]
        self.assertEqual(normalize_employment_slug(raw), "full_time")
        self.assertIn("Full", employment_label_from_raw(raw))

    def test_usajobs_stringified_list(self):
        raw = "[{'Code': '1', 'Name': ''}]"
        self.assertEqual(normalize_employment_slug(raw), "full_time")

    def test_adzuna_contract_time(self):
        self.assertEqual(normalize_employment_slug("full_time"), "full_time")
        self.assertEqual(normalize_employment_slug("part_time"), "part_time")

    def test_empty_employment(self):
        self.assertEqual(normalize_employment_slug(""), "")
        self.assertEqual(normalize_employment_slug("-"), "")

    def test_usajobs_salary_display(self):
        text = format_salary_display(
            salary_min=101401,
            salary_max=185234,
            salary_currency="PA",
            salary_period="PA",
            source="usajobs",
        )
        self.assertIn("$", text)
        self.assertIn("/yr", text)

    def test_usajobs_category_list(self):
        raw = [{"Code": "2152", "Name": "Air Traffic Control"}]
        self.assertEqual(category_label_from_raw(raw), "Air Traffic Control")
        stored = "[{'Code': '2152', 'Name': 'Air Traffic Control'}]"
        self.assertEqual(category_label_from_raw(stored), "Air Traffic Control")

    def test_adzuna_salary_range(self):
        text = format_salary_display(
            salary_min=0,
            salary_max=100000,
            salary_currency="USD",
            salary_period="",
            source="adzuna",
        )
        self.assertIn("100,000", text)
