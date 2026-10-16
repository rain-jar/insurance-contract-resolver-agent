from __future__ import annotations

import re
from typing import Any

from .models import ResolutionResult, ResolutionStatus


def operative_state_correct(expected: dict[str, Any], actual: ResolutionResult) -> bool:
    expected_behavior = expected["expected_behavior"]
    if actual.status.value != expected_behavior:
        return False
    if expected_behavior != ResolutionStatus.ANSWER.value:
        return True
    return _value_dict(actual) == expected["expected_answer"]


def amendment_chain_correct(expected: dict[str, Any], actual: ResolutionResult) -> bool:
    expected_chain = expected["amendment_chain"]
    actual_chain = [
        {
            "source": step.source,
            "operation": step.operation.value,
            "value": _compact_value(step.value),
        }
        for step in actual.amendment_chain
    ]
    return _normalize_chain(actual_chain) == _normalize_chain(expected_chain)


def abstention_correct(expected: dict[str, Any], actual: ResolutionResult) -> bool:
    expected_behavior = expected["expected_behavior"]
    if expected_behavior == ResolutionStatus.ANSWER.value:
        return True
    return actual.status.value == expected_behavior


def _value_dict(actual: ResolutionResult) -> dict[str, Any] | None:
    return _compact_value(actual.normalized_value)


def _compact_value(value) -> dict[str, Any] | None:
    if value is None:
        return None
    return {key: item for key, item in value.model_dump().items() if item is not None}


def _normalize_chain(chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": re.sub(r"\s+", " ", step["source"]).strip().casefold(),
            "operation": step["operation"],
            "value": step["value"],
        }
        for step in chain
    ]
