"""Shared base types for all validators."""

from __future__ import annotations
from pydantic import BaseModel


class ValidationResult(BaseModel):
    valid: bool
    reason_codes: list[str] = []
    details: str | None = None

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        return ValidationResult(
            valid=self.valid and other.valid,
            reason_codes=self.reason_codes + other.reason_codes,
            details=" | ".join(filter(None, [self.details, other.details])) or None,
        )
