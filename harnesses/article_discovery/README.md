# harnesses/article_discovery/

**System 1.** Classifies articles and company signals by type and generates application-relevant angles.

---

## Entry point

```python
from harnesses.article_discovery.v0 import score_articles, ArticleDiscoveryConfig

config = ArticleDiscoveryConfig()
report = score_articles(articles, profile, config)
# report: ArticleDiscoveryReport
```

## Signal types

| Type | Meaning |
|------|---------|
| `hiring_signal` | Active hiring, team growth, new roles mentioned |
| `technical_signal` | Stack, tools, engineering culture, technical challenges |
| `culture_signal` | Team values, working style, internal practices |
| `strategy_signal` | Product direction, funding, acquisitions, pivots |
| `interview_prep_signal` | Process descriptions, question patterns, candidate experience |
| `networking_signal` | Key people, teams to target, alumni mentions |
| `risk_signal` | Layoffs, leadership churn, financial distress |
| `irrelevant` | No actionable signal for job search |

## For each non-irrelevant signal, the harness produces

- `summary` — concise description grounded in source text
- `application_angle` — how to reference this in a cover letter or interview
- `outreach_angle` — how to mention it in a connection request
- `interview_question` — question this signal suggests preparing for
- `confidence` — 0–1, based on source grounding quality

## LLM + heuristic modes

Uses `claude-haiku` when `ANTHROPIC_API_KEY` is set. Falls back to keyword heuristics when the key is absent. Prompt template: `prompts/article_signal_classify.txt`.

## Validation

`harnesses/validators/article_signal.py` blocks signals that invent claims not present in the source text.
