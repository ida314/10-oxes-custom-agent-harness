# skills/company_research/

**System 1.** Web research skills for discovering company intelligence beyond ATS postings.

---

## Skills

### `find_careers_page/`
Locates the company's main careers URL. Used as the ATS fallback when no board token is known.

**Input:** `company_name`, `domain`
**Output:** `url`, `confidence`

### `find_engineering_blog/`
Discovers the company's engineering blog URL and recent post URLs.

**Input:** `company_name`, `domain`
**Output:** list of `{url, title, published_at}`

### `find_events/`
Discovers upcoming events: hackathons, info sessions, career fairs, conferences.

**Input:** `company_name`, `domain`
**Output:** list of `{title, url, event_date, event_type}`

### `find_recent_articles/`
Discovers recent news articles, press releases, and interviews about the company.

**Input:** `company_name`, `domain`
**Output:** list of `{title, url, published_at, source_type}`

---

## Usage

```python
from skills.company_research.find_recent_articles.skill import FindRecentArticlesSkill
from skills.base import RunContext

skill = FindRecentArticlesSkill()
result = skill.run({"company_name": "Stripe", "domain": "stripe.com"}, RunContext())

for article in result.items:
    print(article["title"], article["url"])
```

---

## Notes

- All skills use HTTP only — no browser automation
- Results are passed to `harnesses/article_discovery/v0.py` for signal classification
- `find_engineering_blog` and `find_events` do not yet have dedicated fixture tests (see `docs/STATE.md`)
