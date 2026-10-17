from contract_stack.models import (
    Attribute,
    EvidenceRef,
    ExtractionMethod,
    NormalizedValue,
    Operation,
    OrderingInfo,
    ProvisionEvent,
    QuerySpec,
    ResolutionStatus,
    SourceRef,
)
from contract_stack.reducer import reduce_provisions
from contract_stack.resolver import _normalize_source_label


def _value(*, amount=None, currency=None, start=None, end=None) -> NormalizedValue:
    return NormalizedValue(amount=amount, currency=currency, start=start, end=end)


def _event(
    label: str,
    operation: Operation,
    value: NormalizedValue | None,
    *,
    number: int | None = None,
    required: list[str] | None = None,
    supersedes: list[str] | None = None,
    attribute: Attribute = Attribute.LIMIT,
    document_path: str | None = None,
) -> ProvisionEvent:
    return ProvisionEvent(
        attribute=attribute,
        subject="On Premises" if attribute != Attribute.POLICY_PERIOD else "Policy Period",
        operation=operation,
        value=value,
        source=SourceRef(
            document_path=document_path or f"{label}.txt",
            provision_label=label,
            locator="paragraph:1",
        ),
        evidence=[
            EvidenceRef(
                document_path=document_path or f"{label}.txt",
                locator="paragraph:1",
                quote=f"Evidence for {label}",
                extraction_method=ExtractionMethod.TEXT,
            )
        ],
        ordering=OrderingInfo(
            order_number=number,
            effective_date=None,
            required_sources=required or [],
            supersedes=supersedes or [],
        ),
    )


def test_numbered_replacements_are_reduced_in_order() -> None:
    query = QuerySpec(attribute=Attribute.LIMIT, subject="On Premises")
    events = [
        _event("Endorsement 8", Operation.DELETE_AND_RESTATE, _value(amount=5_000_000, currency="USD"), number=8),
        _event("Base declarations Item 2", Operation.BASE, _value(amount=3_500_000, currency="USD")),
        _event("Endorsement 7", Operation.DELETE_AND_RESTATE, _value(amount=4_250_000, currency="USD"), number=7),
    ]

    outcome = reduce_provisions(query, events)

    assert outcome.result.status == ResolutionStatus.ANSWER
    assert outcome.result.normalized_value == _value(amount=5_000_000, currency="USD")
    assert [step.source for step in outcome.result.amendment_chain] == [
        "Base declarations Item 2",
        "Endorsement 7",
        "Endorsement 8",
    ]


def test_partial_amendment_carries_forward_unchanged_period_field() -> None:
    query = QuerySpec(attribute=Attribute.POLICY_PERIOD, subject="Policy Period")
    events = [
        _event(
            "Rider 18",
            Operation.AMEND,
            _value(start="2026-06-30T12:00:00", end="2027-09-30T12:00:00"),
            number=18,
            attribute=Attribute.POLICY_PERIOD,
        ),
        _event(
            "Rider 19",
            Operation.AMEND,
            _value(end="2027-12-31T12:00:00"),
            number=19,
            attribute=Attribute.POLICY_PERIOD,
        ),
        _event(
            "Rider 20",
            Operation.AMEND,
            _value(start="2027-03-01T12:00:00"),
            number=20,
            attribute=Attribute.POLICY_PERIOD,
        ),
    ]

    outcome = reduce_provisions(query, events)

    assert outcome.result.normalized_value == _value(
        start="2027-03-01T12:00:00", end="2027-12-31T12:00:00"
    )
    assert outcome.result.amendment_chain[-1].value == outcome.result.normalized_value


def test_explicit_supersession_is_inspectable() -> None:
    query = QuerySpec(attribute=Attribute.LIMIT, subject="On Premises")
    events = [
        _event("Endorsement 8", Operation.REPLACE, _value(amount=2_000_000, currency="USD"), number=8),
        _event(
            "Endorsement 11",
            Operation.SUPERSEDE,
            _value(amount=3_000_000, currency="USD"),
            number=11,
            supersedes=["Endorsement 8"],
        ),
    ]

    outcome = reduce_provisions(query, events)

    assert outcome.result.normalized_value.amount == 3_000_000
    assert any(relation.basis.value == "EXPLICIT_SUPERSESSION" for relation in outcome.relationships)


def test_unordered_conflicting_amendments_abstain() -> None:
    query = QuerySpec(attribute=Attribute.LIMIT, subject="On Premises")
    events = [
        _event("Amendment A", Operation.REPLACE, _value(amount=5_000_000, currency="USD")),
        _event("Amendment B", Operation.REPLACE, _value(amount=6_000_000, currency="USD")),
    ]

    outcome = reduce_provisions(query, events)

    assert outcome.result.status == ResolutionStatus.INSUFFICIENT_EVIDENCE
    assert "Precedence is unresolved" in outcome.result.reason
    assert outcome.result.amendment_chain == []


def test_missing_required_source_abstains() -> None:
    query = QuerySpec(attribute=Attribute.DEDUCTIBLE, subject="On Premises")
    event = _event(
        "Endorsement 8",
        Operation.REPLACE,
        None,
        number=8,
        required=["Schedule A"],
        attribute=Attribute.DEDUCTIBLE,
    )

    outcome = reduce_provisions(query, [event])

    assert outcome.result.status == ResolutionStatus.INSUFFICIENT_EVIDENCE
    assert "Schedule A" in outcome.result.reason


def test_source_label_normalization_removes_only_provenance_annotation() -> None:
    event = _event(
        "Endorsement 8 (synthetic controlled)",
        Operation.REPLACE,
        _value(amount=5_000_000, currency="USD"),
        number=8,
    )

    normalized = _normalize_source_label(event)

    assert normalized.source.provision_label == "Endorsement 8"
    assert normalized.source.document_path == event.source.document_path
    assert normalized.evidence == event.evidence


def test_equivalent_base_extractions_from_one_document_are_coalesced() -> None:
    query = QuerySpec(attribute=Attribute.POLICY_PERIOD, subject="Policy Period")
    base_value = _value(start="2026-06-30T00:01:00", end="2027-06-30T00:01:00")
    amended_value = _value(start="2026-06-30T12:00:00", end="2027-06-30T12:00:00")
    events = [
        _event(
            "Base risk details Bond Period",
            Operation.BASE,
            base_value,
            attribute=Attribute.POLICY_PERIOD,
            document_path="policy.pdf",
        ),
        _event(
            "Base declarations Item 2",
            Operation.BASE,
            base_value,
            attribute=Attribute.POLICY_PERIOD,
            document_path="policy.pdf",
        ),
        _event(
            "Rider 17",
            Operation.AMEND,
            amended_value,
            number=17,
            required=["Base declarations Item 2"],
            attribute=Attribute.POLICY_PERIOD,
            document_path="policy.pdf",
        ),
    ]

    outcome = reduce_provisions(query, events)

    assert outcome.result.status == ResolutionStatus.ANSWER
    assert outcome.result.normalized_value == amended_value
    assert [step.source for step in outcome.result.amendment_chain] == [
        "Rider 17",
    ]
    assert len(outcome.result.evidence) == 3


def test_complete_first_amendment_roots_operative_chain_but_preserves_base_evidence() -> None:
    query = QuerySpec(attribute=Attribute.POLICY_PERIOD, subject="Policy Period")
    base = _event(
        "Base declarations Item 2",
        Operation.BASE,
        _value(start="2026-06-30T00:01:00", end="2027-06-30T00:01:00"),
        attribute=Attribute.POLICY_PERIOD,
    )
    amendment = _event(
        "Rider 17",
        Operation.AMEND,
        _value(start="2026-06-30T12:00:00", end="2027-06-30T12:00:00"),
        number=17,
        required=["Base declarations Item 2"],
        attribute=Attribute.POLICY_PERIOD,
    )

    outcome = reduce_provisions(query, [base, amendment])

    assert [event.source.provision_label for event in outcome.ordered_events] == [
        "Base declarations Item 2",
        "Rider 17",
    ]
    assert [step.source for step in outcome.result.amendment_chain] == ["Rider 17"]
    assert {item.quote for item in outcome.result.evidence} == {
        "Evidence for Base declarations Item 2",
        "Evidence for Rider 17",
    }


def test_partial_first_amendment_does_not_remove_base_from_chain() -> None:
    query = QuerySpec(attribute=Attribute.POLICY_PERIOD, subject="Policy Period")
    events = [
        _event(
            "Base declarations Item 2",
            Operation.BASE,
            _value(start="2026-06-30T00:01:00", end="2027-06-30T00:01:00"),
            attribute=Attribute.POLICY_PERIOD,
        ),
        _event(
            "Rider 18",
            Operation.AMEND,
            _value(end="2027-09-30T12:00:00"),
            number=18,
            attribute=Attribute.POLICY_PERIOD,
        ),
    ]

    outcome = reduce_provisions(query, events)

    assert [step.source for step in outcome.result.amendment_chain] == [
        "Base declarations Item 2",
        "Rider 18",
    ]


def test_distinct_base_values_are_not_coalesced() -> None:
    query = QuerySpec(attribute=Attribute.LIMIT, subject="On Premises")
    events = [
        _event(
            "Base schedule A",
            Operation.BASE,
            _value(amount=1_000_000, currency="USD"),
            document_path="policy.pdf",
        ),
        _event(
            "Base schedule B",
            Operation.BASE,
            _value(amount=2_000_000, currency="USD"),
            document_path="policy.pdf",
        ),
    ]

    outcome = reduce_provisions(query, events)

    assert outcome.result.status == ResolutionStatus.INSUFFICIENT_EVIDENCE
    assert "Precedence is unresolved" in outcome.result.reason
