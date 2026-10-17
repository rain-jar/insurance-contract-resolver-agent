from contract_stack.models import (
    Attribute,
    Chunk,
    ExtractionMethod,
    NormalizedValue,
    Operation,
    OrderingInfo,
    ProvisionEvent,
    QuerySpec,
    RetrievedChunk,
    SourceRef,
)
from contract_stack.relationship_retrieval import BoundedRelationshipRetriever


def test_bounded_expansion_recovers_earlier_attribute_specific_rider() -> None:
    base = _chunk("base", "ITEM 2. Bond Period runs from June 2026 to June 2027.")
    rider_18 = _chunk("r18", "Rider 18: Bond Period expiration is amended.")
    rider_17 = _chunk(
        "r17",
        "RIDER 17 Item 2. Bond Period is amended to read from June 2026 to June 2027.",
    )
    unrelated = _chunk("r16", "RIDER 16 Mailing address is amended.")
    initial = [
        RetrievedChunk(chunk=base, score=1.0, rank=1),
        RetrievedChunk(chunk=rider_18, score=0.9, rank=2),
    ]
    events = [
        _event(
            "Base declarations Item 2",
            Operation.BASE,
            None,
            attribute=Attribute.POLICY_PERIOD,
        ),
        _event(
            "Rider 18",
            Operation.AMEND,
            NormalizedValue(amount=None, currency=None, start=None, end="2027-09-30T12:00:00"),
            number=18,
            document_path="controlled-rider.txt",
        ),
    ]

    expansion = BoundedRelationshipRetriever(max_added_chunks=2).expand(
        QuerySpec(attribute=Attribute.POLICY_PERIOD, subject="Bond Period"),
        [base, rider_18, rider_17, unrelated],
        initial,
        events,
    )

    assert expansion.triggered
    assert "POSSIBLE_MISSING_PREDECESSOR" in expansion.reasons
    assert [item.chunk.chunk_id for item in expansion.added] == ["r17"]
    assert expansion.added[0].rank == 3


def test_unordered_unnumbered_conflict_does_not_trigger_expansion() -> None:
    events = [
        _event("Amendment A", Operation.REPLACE, _money(5_000_000)),
        _event("Amendment B", Operation.REPLACE, _money(6_000_000)),
    ]

    expansion = BoundedRelationshipRetriever().expand(
        QuerySpec(attribute=Attribute.LIMIT, subject="On Premises"),
        [],
        [],
        events,
    )

    assert not expansion.triggered
    assert expansion.added == []


def test_explicit_missing_source_can_be_followed() -> None:
    referenced = _chunk(
        "e9",
        "Endorsement 9 replaces the On Premises limit with USD 5,000,000.",
    )
    event = _event(
        "Endorsement 10",
        Operation.AMEND,
        None,
        number=10,
        required=["Endorsement 9"],
    )

    expansion = BoundedRelationshipRetriever().expand(
        QuerySpec(attribute=Attribute.LIMIT, subject="On Premises"),
        [referenced],
        [],
        [event],
    )

    assert expansion.reasons == ["MISSING_EXPLICIT_SOURCE"]
    assert [item.chunk.chunk_id for item in expansion.added] == ["e9"]


def _event(
    label: str,
    operation: Operation,
    value: NormalizedValue | None,
    *,
    number: int | None = None,
    required: list[str] | None = None,
    attribute: Attribute | None = None,
    document_path: str = "policy.pdf",
) -> ProvisionEvent:
    return ProvisionEvent(
        attribute=attribute or (Attribute.POLICY_PERIOD if "Rider" in label else Attribute.LIMIT),
        subject="Bond Period" if "Rider" in label else "On Premises",
        operation=operation,
        value=value,
        source=SourceRef(
            document_path=document_path,
            provision_label=label,
            locator="page:1",
        ),
        evidence=[],
        ordering=OrderingInfo(
            order_number=number,
            effective_date=None,
            required_sources=required or [],
            supersedes=[],
        ),
    )


def _money(amount: int) -> NormalizedValue:
    return NormalizedValue(amount=amount, currency="USD", start=None, end=None)


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_path="policy.pdf",
        locator=f"page:{chunk_id}",
        text=text,
        extraction_method=ExtractionMethod.TEXT,
    )
