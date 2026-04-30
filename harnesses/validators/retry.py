"""
Retry wrapper (AutoHarness pattern).

validate_with_retry(propose_fn, validate_fn, max_retries) implements:
  1. Call propose_fn()
  2. Call validate_fn(result)
  3. If invalid and retries remain: call propose_fn(feedback=reason_codes) and repeat
  4. If still invalid after max_retries: return (result, validation, routed_to_human=True)
"""

from __future__ import annotations
from typing import Any, Callable
from pydantic import BaseModel
from .base import ValidationResult


class RetryResult(BaseModel):
    result: Any
    validation: ValidationResult
    attempts: int
    routed_to_human: bool


def validate_with_retry(
    propose_fn: Callable[..., Any],
    validate_fn: Callable[[Any], ValidationResult],
    max_retries: int = 1,
    propose_kwargs: dict | None = None,
) -> RetryResult:
    """
    Calls propose_fn(**propose_kwargs), validates, retries with feedback on failure.
    On exhaustion, marks routed_to_human=True.

    propose_fn signature: propose_fn(**kwargs, feedback: list[str] | None = None) -> Any
    validate_fn signature: validate_fn(result) -> ValidationResult
    """
    kwargs = propose_kwargs or {}
    result = propose_fn(**kwargs)
    validation = validate_fn(result)
    attempts = 1

    while not validation.valid and attempts <= max_retries:
        feedback = validation.reason_codes
        result = propose_fn(**kwargs, feedback=feedback)
        validation = validate_fn(result)
        attempts += 1

    routed_to_human = not validation.valid

    return RetryResult(
        result=result,
        validation=validation,
        attempts=attempts,
        routed_to_human=routed_to_human,
    )
