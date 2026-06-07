# harnesses/application_packet/

**System 1.** Generates a validated application packet for a specific job. Never auto-submits anything.

---

## Entry point

```python
from harnesses.application_packet.v0 import generate_application_packet, PacketConfig

config = PacketConfig()
result = generate_application_packet(job_id, profile, config)
# result: ApplicationPacketResult
# result.packet.approval_status is always "pending"
```

## Outputs

| Field | Content |
|-------|---------|
| `cover_letter` | Draft tailored to the job and company signals |
| `resume_tailoring` | Specific bullet rewrites and skill highlights |
| `short_answers` | Drafts for required application questions |
| `referral_request` | Draft outreach to a mutual connection |
| `interview_prep` | Notes derived from article signals and job description |

## Safety guarantees

- Every company-specific claim maps to a source URL from `articles` or `events`
- Every skill claim maps to a field in `CandidateProfile.skills`
- `is_valid_application_packet` blocks altered dates, GPAs, or employer names
- `validate_with_retry` retries on validation failure; routes to human review after `max_retries`
- `approval_status` starts as `"pending"` — never changed automatically

## Approval flow

```
generate_application_packet()
        │
        ▼
is_valid_application_packet()   ← pure Python, no LLM
        │
        ├── valid  →  save to DB  →  create ApprovalItem(status="pending")
        └── invalid →  human review queue (no save)
```
