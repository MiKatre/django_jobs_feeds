#!/usr/bin/env python3

from __future__ import annotations

import unittest

from extractor import Job, dedupe, favicon_url, key_for, parse_salary


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


if __name__ == "__main__":
    unittest.main()
