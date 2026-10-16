from types import SimpleNamespace

from contract_stack.models import (
    Attribute,
    Chunk,
    EvidenceRef,
    ExtractionMethod,
    NormalizedValue,
    Operation,
    OrderingInfo,
    ProvisionEvent,
    ProvisionExtraction,
    ResolutionStatus,
    RetrievedChunk,
    SourceRef,
)
from contract_stack.resolver import ContractStackResolver


class _Usage:
    def model_dump(self, *, mode: str) -> dict[str, int]:
        assert mode == "json"
        return {"input_tokens": 100, "output_tokens": 25, "total_tokens": 125}


class _Responses:
    def __init__(self, extraction: ProvisionExtraction) -> None:
        self.extraction = extraction
        self.called = False

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.called = True
        return SimpleNamespace(
            id="resp_test",
            model="gpt-6.1-sol",
            output_parsed=self.extraction,
            service_tier="default",
            usage=_Usage(),
        )


def _event(label: str, amount: int, operation: Operation, number: int | None) -> ProvisionEvent:
    quote = f"{label} sets the limit to USD {amount:,}."
    return ProvisionEvent(
        attribute=Attribute.LIMIT,
        subject="On Premises",
        operation=operation,
        value=NormalizedValue(amount=amount, currency="USD", start=None, end=None),
        source=SourceRef(document_path="stack.txt", provision_label=label, locator="paragraph:1"),
        evidence=[
            EvidenceRef(
                document_path="stack.txt",
                locator="paragraph:1",
                quote=quote,
                extraction_method=ExtractionMethod.TEXT,
            )
        ],
        ordering=OrderingInfo(
            order_number=number,
            effective_date=None,
            required_sources=[],
            supersedes=[],
        ),
    )


def test_resolver_extracts_then_reduces_with_traceable_evidence() -> None:
    events = [
        _event("Base declarations Item 2", 3_500_000, Operation.BASE, None),
        _event("Endorsement 8", 5_000_000, Operation.REPLACE, 8),
    ]
    text = "\n".join(event.evidence[0].quote for event in events)
    retrieved = [
        RetrievedChunk(
            chunk=Chunk(
                chunk_id="c1",
                document_path="stack.txt",
                locator="paragraph:1",
                text=text,
                extraction_method=ExtractionMethod.TEXT,
            ),
            score=1.0,
            rank=1,
        )
    ]
    responses = _Responses(ProvisionExtraction(events=events))
    client = SimpleNamespace(responses=responses)

    run = ContractStackResolver(client).resolve(
        "What is the current On Premises single loss limit?", retrieved
    )

    assert responses.called
    assert run.result.status == ResolutionStatus.ANSWER
    assert run.result.normalized_value.amount == 5_000_000
    assert [step.source for step in run.result.amendment_chain] == [
        "Base declarations Item 2",
        "Endorsement 8",
    ]
    assert run.extraction_provenance_errors == []
    assert run.relationships


def test_unsupported_attribute_bypasses_model_extraction() -> None:
    responses = _Responses(ProvisionExtraction(events=[]))
    client = SimpleNamespace(responses=responses)

    run = ContractStackResolver(client).resolve("What is the territorial coverage?", [])

    assert run.result.status == ResolutionStatus.UNSUPPORTED_ATTRIBUTE
    assert not responses.called
