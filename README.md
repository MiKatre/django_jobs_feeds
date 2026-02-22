# django_jobs_feeds

Daily-generated Django jobs feeds (JSON + RSS) suitable for GitHub Pages or direct repo consumption.

## Outputs (root level)
- `django_jobs_feed.json`
- `django_jobs_feed.xml`

## Local run
```bash
python3 extractor.py \
  --json-output django_jobs_feed.json \
  --rss-output django_jobs_feed.xml
```

## Tests
```bash
python3 -m unittest test_extractor.py
```

## Automation
A scheduled GitHub Actions workflow updates both feeds daily and commits changes:
- `.github/workflows/update-feeds.yml`

It can also be triggered manually with **Run workflow**.
