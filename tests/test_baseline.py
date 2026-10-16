from types import SimpleNamespace

from contract_stack.baseline import (
    BASELINE_INSTRUCTIONS,
    GENERATION_MODEL,
    MAX_OUTPUT_TOKENS,
    DirectRAGBaseline,
)
from contract_stack.models import (
    Attribute,
    Chunk,
    EvidenceRef,
    ExtractionMethod,
    NormalizedValue,
    OperativeState,
    ResolutionResult,
    ResolutionStatus,
    RetrievedChunk,
    SourceRef,
)


class _Usage:
    def model_dump(self, *, mode: str) -> dict[str, int]:
        assert mode == "json"
        return {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}


class _Responses:
    def __init__(self, result: ResolutionResult) -> None:
        self.result = result
        self.kwargs: dict[str, object] | None = None

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp_test",
            model=GENERATION_MODEL,
            output_parsed=self.result,
            service_tier="default",
            usage=_Usage(),
        )


def _answer() -> ResolutionResult:
    value = NormalizedValue(amount=5_000_000, currency="USD", start=None, end=None)
    return ResolutionResult(
        status=ResolutionStatus.ANSWER,
        attribute=Attribute.LIMIT,
        subject="On Premises",
        operative_state=OperativeState.ACTIVE,
        normalized_value=value,
        effective_source=SourceRef(document_path="policy.txt", provision_label="Item 2", locator="paragraph:1"),
        evidence=[
            EvidenceRef(
                document_path="policy.txt",
                locator="paragraph:1",
                quote="USD 5,000,000",
                extraction_method=ExtractionMethod.TEXT,
            )
        ],
        amendment_chain=[],
        reason="The retrieved provision states the limit.",
    )


def test_baseline_locks_generation_configuration_and_records_usage() -> None:
    responses = _Responses(_answer())
    client = SimpleNamespace(responses=responses)
    retrieved = [
        RetrievedChunk(
            chunk=Chunk(
                chunk_id="c1",
                document_path="policy.txt",
                locator="paragraph:1",
                text="The limit is USD 5,000,000.",
                extraction_method=ExtractionMethod.TEXT,
            ),
            score=1.0,
            rank=1,
        )
    ]

    run = DirectRAGBaseline(client).answer("What is the current On Premises limit?", retrieved)

    assert responses.kwargs is not None
    assert responses.kwargs["model"] == GENERATION_MODEL
    assert responses.kwargs["reasoning"] == {"effort": "medium", "mode": "standard"}
    assert responses.kwargs["service_tier"] == "default"
    assert responses.kwargs["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert "shortest human-readable provision label" in BASELINE_INSTRUCTIONS
    assert "endorsement or rider number" in BASELINE_INSTRUCTIONS
    assert "synthetic controlled" in BASELINE_INSTRUCTIONS
    assert run.api_metadata is not None
    assert run.api_metadata["response_model"] == GENERATION_MODEL
    assert run.api_metadata["usage"] == {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
