from contract_stack.evaluation import amendment_chain_correct, operative_state_correct
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
