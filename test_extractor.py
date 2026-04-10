#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from extractor import PYTHON_RSS, Job, dedupe, favicon_url, key_for, normalize_date, parse_python_jobs, parse_salary, write_rss


class ExtractorUnitTests(unittest.TestCase):
    def test_dedupe_keeps_richer_record(self) -> None:
        sparse = Job(
            id="1",
            title="Senior Django Developer",
            company="Acme",
            url="https://example.com/1",
            source="python.org",
            full_offer_text="short",
        )

        rich = Job(
            id="2",
            title="Senior Django Developer @ Acme",
            company="Acme",
            url="https://example.com/2",
            source="builtwithdjango.com",
            location="Remote",
            skills=["Django"],
            full_offer_text="long long text",
            apply_url="https://apply.example.com/job",
            company_url="https://apply.example.com",
            image_url=favicon_url("https://apply.example.com"),
        )

        out, stats = dedupe([sparse, rich])

        self.assertEqual(stats["duplicates_removed"], 1)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].url, "https://example.com/2")

    def test_favicon_url_pattern(self) -> None:
        icon = favicon_url("https://example.com")
        self.assertIsNotNone(icon)
        self.assertIn("t0.gstatic.com/faviconV2", icon)
        self.assertIn("url=https://example.com", icon)

    def test_key_normalizes_title_variants(self) -> None:
        a = key_for("Senior Django Developer, Acme", "Acme")
        b = key_for("Senior Django Developer @ Acme", "Acme")
        self.assertEqual(a, b)

    def test_parse_salary_ignores_punctuation_noise(self) -> None:
        self.assertIsNone(parse_salary("hello, world"))
        self.assertIsNone(parse_salary("Raised 3.1M and growing month-on-month"))
        self.assertEqual(parse_salary("Salary: $120,000 - $150,000"), "$120,000 - $150,000")

    def test_parse_python_jobs_keeps_rss_item_when_detail_page_404s(self) -> None:
        rss = """
        <rss>
          <channel>
            <item>
              <title>Senior Django Developer, Acme</title>
              <link>https://www.python.org/jobs/1234/</link>
              <description>Remote Django role</description>
              <pubDate>Sun, 15 Mar 2026 12:00:00 +0000</pubDate>
            </item>
          </channel>
        </rss>
        """

        with (
            patch("extractor.fetch", return_value=rss),
            patch("extractor.fetch_optional", return_value=None) as fetch_optional,
        ):
            jobs = parse_python_jobs()

        fetch_optional.assert_called_once_with("https://www.python.org/jobs/1234/")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "1234")
        self.assertEqual(jobs[0].company, "Acme")
        self.assertEqual(jobs[0].summary, "Remote Django role")
        self.assertEqual(jobs[0].date_posted, "2026-03-15T12:00:00+00:00")
        self.assertIsNone(jobs[0].apply_url)
        self.assertIsNone(jobs[0].company_url)

    def test_normalize_date_handles_builtwithdjango_format(self) -> None:
        self.assertEqual(normalize_date("Feb. 2, 2026, 7:53 p.m."), "2026-02-02T19:53:00+00:00")
        self.assertEqual(normalize_date("April 1, 2026, 5:50 p.m."), "2026-04-01T17:50:00+00:00")

    def test_write_rss_uses_normalized_job_date(self) -> None:
        payload = {
            "jobs": [
                {
                    "id": "software-engineer",
                    "title": "Software Engineer @ RINSE",
                    "url": "https://builtwithdjango.com/jobs/2310/software-engineer",
                    "dedupe_key": "software engineer|rinse",
                    "date_posted": normalize_date("Feb. 2, 2026, 7:53 p.m."),
                    "summary": "Remote Django role",
                    "company": "RINSE",
                    "location": "Remote",
                    "salary": None,
                    "company_url": "https://rinse.com",
                    "apply_url": "https://rinse.com/jobs/software-engineer",
                    "image_url": "https://example.com/icon.png",
                }
            ]
        }

        out = Path("/tmp/test_django_jobs_feed.xml")
        write_rss(payload, out)
        xml = out.read_text(encoding="utf-8")

        self.assertIn("<pubDate>Mon, 02 Feb 2026 19:53:00 +0000</pubDate>", xml)


if __name__ == "__main__":
    unittest.main()
