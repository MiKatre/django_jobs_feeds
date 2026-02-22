#!/usr/bin/env python3
"""Unified Django jobs extractor with JSON + RSS outputs and favicon image URLs."""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

PYTHON_RSS = "https://www.python.org/jobs/feed/rss/"
BWD_JOBS = "https://builtwithdjango.com/jobs/"
FAVICON_TMPL = (
    "https://t0.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON"
    "&fallback_opts=TYPE,SIZE,URL&url={url}&size=128"
)
UA = "django-jobs-extractor/3.0"


@dataclass
class Job:
    id: str
    title: str
    company: str | None
    url: str
    source: str
    location: str | None = None
    date_posted: str | None = None
    salary: str | None = None
    employment_type: str | None = None
    skills: list[str] | None = None
    categories: list[str] | None = None
    summary: str | None = None
    full_offer_text: str | None = None
    full_offer_html: str | None = None
    apply_url: str | None = None
    company_url: str | None = None
    image_url: str | None = None
    dedupe_key: str | None = None


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urlopen(req, timeout=40) as response:
        raw = response.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="replace")


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_site_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return None


def favicon_url(company_url: str | None) -> str | None:
    if not company_url:
        return None
    return FAVICON_TMPL.format(url=quote(company_url, safe=":/"))


def parse_salary(text: str) -> str | None:
    keyword_match = re.search(
        r"(?i)(?:salary|compensation)[^\d$]{0,20}(\$?\d[\d,]*(?:[kKmM])?(?:\s*[–\-]\s*\$?\d[\d,]*(?:[kKmM])?)?)",
        text,
    )
    if keyword_match:
        return keyword_match.group(1).strip()

    dollar_match = re.search(r"(\$\d[\d,]*(?:\.\d+)?(?:[kKmM])?(?:\s*[–\-]\s*\$\d[\d,]*(?:\.\d+)?(?:[kKmM])?)?)", text)
    if dollar_match:
        return dollar_match.group(1).strip()

    return None


def parse_employment(text: str) -> str | None:
    match = re.search(r"(?i)\b(full[-\s]?time|part[-\s]?time|contract|temporary|intern(ship)?)\b", text)
    return match.group(1).strip() if match else None


def skills_from_text(text: str) -> list[str]:
    keys = ["django", "python", "postgresql", "aws", "kubernetes", "docker", "rest", "api", "pytest", "sql", "react"]
    found = [k for k in keys if k in text.lower()]
    cases = {"aws": "AWS", "api": "API", "rest": "REST", "sql": "SQL"}
    return [cases.get(k, k.capitalize()) for k in found]


def norm(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def key_for(title: str | None, company: str | None) -> str:
    raw_title = (title or "").lower().strip()
    if "@" in raw_title:
        raw_title = raw_title.split("@", 1)[0].strip()
    if "," in raw_title:
        raw_title = raw_title.split(",", 1)[0].strip()
    return f"{norm(raw_title)}|{norm(company)}"


def parse_python_jobs() -> list[Job]:
    root = ET.fromstring(fetch(PYTHON_RSS))
    jobs: list[Job] = []

    for item in root.findall("./channel/item"):
        title = item.findtext("title", default="").strip()
        desc = item.findtext("description", default="").strip()
        if "django" not in f"{title} {desc}".lower():
            continue

        url = item.findtext("link", default="").strip()
        page = fetch(url)

        location = re.search(r'<span class="listing-location">\s*(.*?)\s*</span>', page, flags=re.S | re.I)
        posted = re.search(r'<span class="listing-posted">\s*Posted\s*<time[^>]*datetime="([^"]+)"', page, flags=re.S | re.I)
        categories = [
            strip_tags(value)
            for value in re.findall(r'<span class="listing-company-category">\s*(.*?)\s*</span>', page, flags=re.S | re.I)
            if strip_tags(value)
        ]

        web_link = re.search(r'<li><strong>Web</strong>:\s*<a[^>]*href="([^"]+)"', page, flags=re.S | re.I)
        apply_link = re.search(r'href="(mailto:[^"]+|https?://[^"]+)"[^>]*>\s*Apply', page, flags=re.S | re.I)

        start = page.find('<div class="job-description">')
        end = page.find('<p class="job-meta"', start) if start != -1 else -1
        if end == -1 and start != -1:
            end = page.find("</article>", start)

        full_html = page[start:end] if start != -1 else ""
        full_text = strip_tags(full_html) if full_html else strip_tags(desc)

        pub = item.findtext("pubDate", default="").strip()
        pub_iso = None
        if pub:
            try:
                pub_iso = parsedate_to_datetime(pub).isoformat()
            except Exception:
                pub_iso = pub

        company = title.split(",", 1)[1].strip() if "," in title else None
        apply_url = html.unescape(apply_link.group(1)) if apply_link else None
        company_url = canonical_site_url(html.unescape(web_link.group(1)) if web_link else apply_url)

        job = Job(
            id=urlparse(url).path.rstrip("/").split("/")[-1],
            title=title,
            company=company,
            url=url,
            source="python.org",
            location=strip_tags(location.group(1)) if location else None,
            date_posted=posted.group(1).strip() if posted else pub_iso,
            salary=parse_salary(full_text),
            employment_type=parse_employment(full_text),
            skills=skills_from_text(full_text),
            categories=categories or None,
            summary=full_text[:500],
            full_offer_text=full_text,
            full_offer_html=full_html or None,
            apply_url=apply_url,
            company_url=company_url,
            image_url=favicon_url(company_url),
        )
        job.dedupe_key = key_for(job.title, job.company)
        jobs.append(job)

    return jobs


def parse_bwd_jobs() -> list[Job]:
    listing = fetch(BWD_JOBS)
    jobs: list[Job] = []

    for href in sorted(set(re.findall(r'href="(/jobs/\d+/[^"]+)"', listing))):
        url = urljoin(BWD_JOBS, href)
        page = fetch(url)

        h1 = re.search(r'<h1 class="text-center">\s*(.*?)\s*</h1>', page, flags=re.S)
        title = strip_tags(h1.group(1)) if h1 else ""
        company = title.split("@", 1)[1].strip() if "@" in title else None

        block = re.search(r'<div class="prose md:prose-lg">\s*(.*?)\s*</div>', page, flags=re.S)
        full_html = block.group(1) if block else ""
        full_text = strip_tags(full_html)

        location = re.search(r'Location:\s*</b>\s*(.*?)\s*</p>', page, flags=re.S | re.I)
        salary = re.search(r'Salary:\s*</b>\s*(.*?)\s*</p>', page, flags=re.S | re.I)
        posted = re.search(r'Job Posted:\s*<b>(.*?)</b>', page, flags=re.S | re.I)
        apply = re.search(r'href="(https?://[^"]+)"[^>]*>\s*Apply for this position\s*</a>', page, flags=re.S | re.I)

        ld_match = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', page, flags=re.S)
        ld: dict = {}
        if ld_match:
            try:
                ld = json.loads(ld_match.group(1))
            except Exception:
                ld = {}

        apply_url = ld.get("url") or (html.unescape(apply.group(1)) if apply else None)
        company_url = canonical_site_url(apply_url)

        job = Job(
            id=urlparse(url).path.rstrip("/").split("/")[-1],
            title=title,
            company=((ld.get("hiringOrganization", {}) or {}).get("name") if isinstance(ld.get("hiringOrganization", {}), dict) else None) or company,
            url=url,
            source="builtwithdjango.com",
            location=strip_tags(location.group(1)) if location else ((ld.get("jobLocation", {}) or {}).get("address") if isinstance(ld.get("jobLocation", {}), dict) else None),
            date_posted=ld.get("datePosted") or (strip_tags(posted.group(1)) if posted else None),
            salary=parse_salary(strip_tags(salary.group(1))) if salary else None,
            employment_type=ld.get("employmentType") or parse_employment(full_text),
            skills=skills_from_text(f"{title}\n{full_text}"),
            categories=["Django Job Board"],
            summary=full_text[:500] if full_text else None,
            full_offer_text=full_text,
            full_offer_html=full_html,
            apply_url=apply_url,
            company_url=company_url,
            image_url=favicon_url(company_url),
        )
        job.dedupe_key = key_for(job.title, job.company)
        jobs.append(job)

    return jobs


def score(job: Job) -> int:
    fields = [
        job.company,
        job.location,
        job.date_posted,
        job.salary,
        job.employment_type,
        job.skills,
        job.full_offer_text,
        job.apply_url,
        job.company_url,
        job.image_url,
    ]
    return sum(1 for field in fields if field)


def dedupe(jobs: list[Job]) -> tuple[list[Job], dict]:
    by_key: dict[str, Job] = {}
    for job in jobs:
        key = key_for(job.title, job.company)
        job.dedupe_key = key
        if key not in by_key:
            by_key[key] = job
            continue

        existing = by_key[key]
        if score(job) > score(existing) or (
            score(job) == score(existing)
            and len(job.full_offer_text or "") > len(existing.full_offer_text or "")
        ):
            by_key[key] = job

    deduped = list(by_key.values())
    return deduped, {
        "input_count": len(jobs),
        "output_count": len(deduped),
        "duplicates_removed": len(jobs) - len(deduped),
    }


def build_feed() -> dict:
    python_jobs = parse_python_jobs()
    bwd_jobs = parse_bwd_jobs()
    merged, stats = dedupe(python_jobs + bwd_jobs)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [PYTHON_RSS, BWD_JOBS],
        "counts": {
            "python_org": len(python_jobs),
            "builtwithdjango": len(bwd_jobs),
            **stats,
        },
        "jobs": [asdict(job) for job in merged],
    }


def as_rfc2822(value: str | None) -> str:
    if not value:
        return format_datetime(datetime.now(timezone.utc))

    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        try:
            parsed = datetime.fromisoformat(value)
        except Exception:
            parsed = datetime.now(timezone.utc)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return format_datetime(parsed)


def write_rss(payload: dict, path: Path) -> None:
    channel_items = []
    for job in payload["jobs"]:
        desc = html.escape(job.get("summary") or job.get("full_offer_text") or "")
        company = html.escape(job.get("company") or "")
        location = html.escape(job.get("location") or "")
        salary = html.escape(job.get("salary") or "")
        image_url = html.escape(job.get("image_url") or "")
        company_url = html.escape(job.get("company_url") or "")
        apply_url = html.escape(job.get("apply_url") or "")
        pub_date = as_rfc2822(job.get("date_posted"))

        item = (
            "<item>"
            f"<title>{html.escape(job.get('title') or '')}</title>"
            f"<link>{html.escape(job.get('url') or '')}</link>"
            f"<guid isPermaLink=\"false\">{html.escape(job.get('dedupe_key') or job.get('id') or '')}</guid>"
            f"<pubDate>{html.escape(pub_date)}</pubDate>"
            f"<description>{desc}</description>"
            f"<company>{company}</company>"
            f"<location>{location}</location>"
            f"<salary>{salary}</salary>"
            f"<company_url>{company_url}</company_url>"
            f"<apply_url>{apply_url}</apply_url>"
            f"<image_url>{image_url}</image_url>"
            "</item>"
        )
        channel_items.append(item)

    rss = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<rss version=\"2.0\"><channel>"
        "<title>Django Jobs Unified Feed</title>"
        "<link>https://www.python.org/jobs/</link>"
        "<description>Unified deduplicated Django jobs feed</description>"
        f"<lastBuildDate>{html.escape(format_datetime(datetime.now(timezone.utc)))}</lastBuildDate>"
        + "".join(channel_items)
        + "</channel></rss>"
    )
    path.write_text(rss + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", default="django_jobs_feed.json")
    parser.add_argument("--rss-output", default="django_jobs_feed.xml")
    args = parser.parse_args()

    payload = build_feed()

    json_path = Path(args.json_output)
    rss_path = Path(args.rss_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    rss_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_rss(payload, rss_path)

    print(json.dumps(payload["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
