# app/

**Shared infrastructure.** Application-level modules used by both systems.

---

## `tracing/logger.py` — TraceLogger

Used by every harness to write raw execution traces to `experiments/runs/{ts}/`.

```python
from app.tracing.logger import TraceLogger

logger = TraceLogger(harness_name="job_discovery", version="v0")
logger.save_config(config.model_dump())
logger.log("skill_greenhouse", result.model_dump())
logger.log("prompt_score_jobs", prompt_text)
logger.log("model_output_score_jobs", llm_response)
logger.log("validator_result", validation_result.model_dump())
logger.log_failure("false_positive", job.model_dump())
logger.save_output(report.model_dump())
logger.save_metrics({"job_recall": 0.85})
```

### Methods

| Method | Writes |
|--------|--------|
| `save_config(data)` | `000_config.json` |
| `log(name, data)` | `{seq:03d}_{name}.json` or `.txt` |
| `log_failure(category, data)` | `failures/{category}_{n}.json` |
| `save_output(data)` | `output.json` |
| `save_metrics(data)` | `metrics.json` |
| `snapshot_harness_source(path)` | `harness.py` (snapshot of the running harness) |

### Trace directory layout

```
experiments/runs/{ISO_TIMESTAMP}_{harness}_{version}/
  000_config.json
  001_skill_{name}.json
  002_prompt_{name}.txt
  003_model_output_{name}.txt
  004_validator_result.json
  ...
  output.json
  metrics.json
  failures/
    false_positives_0.json
    missed_jobs_0.json
```

The proposer agent (System 2) reads these directories with standard file tools (`grep`, `cat`). Never compress or summarize trace content — verbatim content is what enables failure diagnosis.
