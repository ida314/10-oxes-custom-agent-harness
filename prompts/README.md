# prompts/

**System 1.** LLM prompt templates used by harnesses. Never inline long prompts in Python.

---

## Files

### `article_signal_classify.txt`
Used by `harnesses/article_discovery/v0.py` to classify article signal type and extract application angles.

Inputs (template variables):
- `{article_title}`
- `{article_text}`
- `{candidate_skills}`
- `{target_role}`

### `cover_letter_draft.txt`
Used by `harnesses/application_packet/v0.py` to draft a tailored cover letter.

Inputs (template variables):
- `{job_title}`
- `{company_name}`
- `{job_description_excerpt}`
- `{candidate_profile_summary}`
- `{article_signals}` — company intelligence to reference

---

## Conventions

- Use `{variable_name}` for template substitution in Python (`str.format_map(...)`)
- Keep prompts focused: one task per template
- Include the validation criteria in the prompt so the model's output structure matches what the validator expects
- When a prompt changes significantly, keep the old version commented with a date — prompt diffs are part of the harness history
