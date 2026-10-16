from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .models import ResolutionResult, ResolutionStatus, SourceRef


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


def evidence_accuracy_errors(
    expected: dict[str, Any],
    actual: ResolutionResult,
    provenance_errors: list[str],
) -> list[str] | None:
    """Apply the approved deterministic Stage 5 evidence rubric.

    Non-answer cases are excluded because their safe behavior is measured by the
    abstention metric. Answer cases require grounded citations, the expected
    effective source, a citation at the result's effective locator, and quoted
    support for every normalized expected-value component.
    """
    if expected["expected_behavior"] != ResolutionStatus.ANSWER.value:
        return None

    errors: list[str] = []
    if actual.status != ResolutionStatus.ANSWER:
        return ["The system did not return an ANSWER result."]
    if provenance_errors:
        errors.append("One or more evidence citations failed provenance validation.")
    if actual.effective_source is None:
        errors.append("The answer has no effective source.")
    elif not _source_matches(expected["effective_source"], actual.effective_source):
        errors.append("The effective source does not match the benchmark effective source.")
    elif not any(_same_locator(item, actual.effective_source) for item in actual.evidence):
        errors.append("No evidence citation points to the effective source locator.")
    if not actual.evidence:
        errors.append("The answer has no evidence citations.")
        return errors

    expected_value = expected["expected_answer"]
    quotes = [item.quote for item in actual.evidence]
    if "amount" in expected_value and not _amount_and_currency_supported(
        quotes,
        expected_value["amount"],
        expected_value.get("currency"),
    ):
        errors.append("The evidence does not quote the expected amount and currency.")
    for field in ("start", "end"):
        value = expected_value.get(field)
        if value is not None and not any(_quote_contains_date(quote, value) for quote in quotes):
            errors.append(f"The evidence does not quote the expected {field} date.")
    return errors


def evidence_accurate(
    expected: dict[str, Any],
    actual: ResolutionResult,
    provenance_errors: list[str],
) -> bool | None:
    errors = evidence_accuracy_errors(expected, actual, provenance_errors)
    return None if errors is None else not errors


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


def _source_matches(expected: str, actual: SourceRef) -> bool:
    expected_path = expected.replace("\\", "/").casefold()
    actual_path = actual.document_path.replace("\\", "/").casefold()
    if "/" in expected_path or expected_path.endswith((".pdf", ".html", ".txt")):
        return expected_path == actual_path

    expected_number = _document_number(expected)
    actual_number = _document_number(actual.provision_label or "")
    if expected_number is not None:
        return expected_number == actual_number

    expected_label = _canonical_source(expected)
    actual_label = _canonical_source(actual.provision_label or "")
    return bool(expected_label and actual_label) and (
        expected_label in actual_label or actual_label in expected_label
    )


def _document_number(value: str) -> tuple[str, int] | None:
    match = re.search(r"\b(endorsement|rider)\s*(?:number|no\.?\s*)?(\d+)\b", value, re.I)
    return (match.group(1).casefold(), int(match.group(2))) if match else None


def _canonical_source(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _same_locator(evidence, source: SourceRef) -> bool:
    return (
        evidence.document_path.replace("\\", "/").casefold()
        == source.document_path.replace("\\", "/").casefold()
        and evidence.locator.casefold() == source.locator.casefold()
    )


def _amount_and_currency_supported(
    quotes: list[str], amount: int, currency: str | None
) -> bool:
    for quote in quotes:
        amounts = {
            int(match.group(1).replace(",", "").replace(" ", ""))
            for match in re.finditer(
                r"(?<!\d)(?:USD\s*)?\$?\s*(\d{1,3}(?:[, ]\s*\d{3})+|\d+)(?!\d)",
                quote,
                re.I,
            )
        }
        currency_supported = currency is None or (
            currency.casefold() == "usd" and ("$" in quote or re.search(r"\bUSD\b", quote, re.I))
        )
        if amount in amounts and currency_supported:
            return True
    return False


def _quote_contains_date(quote: str, iso_value: str) -> bool:
    value = datetime.fromisoformat(iso_value)
    month_names = (
        "january|february|march|april|may|june|july|august|"
        "september|october|november|december"
    )
    month_name = month_names.split("|")[value.month - 1]
    day = str(value.day)
    year = str(value.year)
    patterns = [
        rf"\b0?{day}[^\w]{{1,3}}{month_name}\s+{year}\b",
        rf"\b{month_name}\s+0?{day}[^\w]{{0,2}}\s*{year}\b",
        rf"\b{year}-0?{value.month}-0?{day}\b",
        rf"\b0?{value.month}/0?{day}/{year}\b",
        rf"\b0?{day}/0?{value.month}/{year}\b",
    ]
    return any(re.search(pattern, quote, re.I) for pattern in patterns)
