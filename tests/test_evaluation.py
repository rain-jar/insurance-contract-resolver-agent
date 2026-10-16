from contract_stack.evaluation import (
    amendment_chain_correct,
    evidence_accuracy_errors,
    evidence_accurate,
    operative_state_correct,
)
from contract_stack.models import (
    Attribute,
    ChainStep,
    EvidenceRef,
    ExtractionMethod,
    NormalizedValue,
    OperativeState,
    Operation,
    ResolutionResult,
    ResolutionStatus,
    SourceRef,
)


def _answer() -> ResolutionResult:
    value = NormalizedValue(amount=5_000_000, currency="USD", start=None, end=None)
    return ResolutionResult(
        status=ResolutionStatus.ANSWER,
        attribute=Attribute.LIMIT,
        subject="On Premises",
        operative_state=OperativeState.ACTIVE,
        normalized_value=value,
        effective_source=SourceRef(
            document_path="endorsement.txt",
            provision_label="Endorsement 8",
            locator="paragraph:1",
        ),
        evidence=[
            EvidenceRef(
                document_path="endorsement.txt",
                locator="paragraph:1",
                quote="Limit USD 5,000,000",
                extraction_method=ExtractionMethod.TEXT,
            )
        ],
        amendment_chain=[ChainStep(source="Endorsement 8", operation=Operation.REPLACE, value=value)],
        reason="Supported by Endorsement 8.",
    )


def test_answer_and_chain_metrics_are_separate() -> None:
    expected = {
        "expected_behavior": "ANSWER",
        "expected_answer": {"amount": 5_000_000, "currency": "USD"},
        "amendment_chain": [
            {"source": "Endorsement 8", "operation": "REPLACE", "value": {"amount": 5_000_000, "currency": "USD"}}
        ],
    }
    actual = _answer()
    assert operative_state_correct(expected, actual)
    assert amendment_chain_correct(expected, actual)


def test_evidence_accuracy_requires_expected_source_value_and_grounding() -> None:
    expected = {
        "expected_behavior": "ANSWER",
        "expected_answer": {"amount": 5_000_000, "currency": "USD"},
        "effective_source": "Endorsement 8 — Amend Item 2",
    }
    actual = _answer()

    assert evidence_accuracy_errors(expected, actual, []) == []
    assert evidence_accurate(expected, actual, []) is True
    assert evidence_accurate(expected, actual, ["quote not found"]) is False


def test_evidence_accuracy_supports_partial_period_across_citations() -> None:
    actual = ResolutionResult(
        status=ResolutionStatus.ANSWER,
        attribute=Attribute.POLICY_PERIOD,
        subject="Bond Period",
        operative_state=OperativeState.ACTIVE,
        normalized_value=NormalizedValue(
            amount=None,
            currency=None,
            start="2027-03-01T12:00:00",
            end="2027-12-31T12:00:00",
        ),
        effective_source=SourceRef(
            document_path="documents/controlled/rider20.txt",
            provision_label="Rider 20",
            locator="paragraph:1",
        ),
        evidence=[
            EvidenceRef(
                document_path="documents/controlled/rider19.txt",
                locator="paragraph:1",
                quote="Expiration is 31 December 2027 at 12:00 noon.",
                extraction_method=ExtractionMethod.TEXT,
            ),
            EvidenceRef(
                document_path="documents/controlled/rider20.txt",
                locator="paragraph:1",
                quote="Inception is replaced by 1 March 2027 at 12:00 noon.",
                extraction_method=ExtractionMethod.TEXT,
            ),
        ],
        amendment_chain=[],
        reason="Rider 20 changes inception only.",
    )
    expected = {
        "expected_behavior": "ANSWER",
        "expected_answer": {
            "start": "2027-03-01T12:00:00",
            "end": "2027-12-31T12:00:00",
        },
        "effective_source": "documents/controlled/rider20.txt",
    }

    assert evidence_accuracy_errors(expected, actual, []) == []


def test_evidence_accuracy_excludes_non_answer_cases() -> None:
    expected = {
        "expected_behavior": "INSUFFICIENT_EVIDENCE",
        "expected_answer": None,
        "effective_source": None,
    }

    assert evidence_accurate(expected, _answer(), []) is None
