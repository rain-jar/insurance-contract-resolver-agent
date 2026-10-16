from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (
    Attribute,
    ChainStep,
    EvidenceRef,
    NormalizedValue,
    Operation,
    OperativeState,
    ProvisionEvent,
    ProvisionRelationship,
    QuerySpec,
    RelationshipBasis,
    ResolutionResult,
    ResolutionStatus,
)


@dataclass(frozen=True)
class ReductionOutcome:
    result: ResolutionResult
    ordered_events: list[ProvisionEvent]
    relationships: list[ProvisionRelationship]


def reduce_provisions(query: QuerySpec, events: list[ProvisionEvent]) -> ReductionOutcome:
    relevant = [event for event in events if event.attribute == query.attribute]
    if not relevant:
        return _insufficient(query, "No relevant provision events were extracted.")

    relevant, duplicate_error = _deduplicate(relevant)
    if duplicate_error:
        return _insufficient(query, duplicate_error)

    labels = {_canonical(_label(event)) for event in relevant}
    missing = sorted(
        {
            required
            for event in relevant
            for required in event.ordering.required_sources
            if _canonical(required) not in labels
        }
    )
    if missing:
        return _insufficient(
            query,
            "Required referenced sources are missing: " + ", ".join(missing) + ".",
        )

    ordered, relationships, ordering_error = _order_events(relevant)
    if ordering_error:
        return _insufficient(query, ordering_error, relationships=relationships)

    current: NormalizedValue | None = None
    active = False
    chain: list[ChainStep] = []
    for event in ordered:
        if not event.evidence:
            return _insufficient(
                query,
                f"{_label(event)} has no traceable supporting evidence.",
                ordered_events=ordered,
                relationships=relationships,
            )
        if event.operation == Operation.DELETE:
            current = None
            active = False
        elif event.operation == Operation.AMEND:
            if event.value is None:
                return _insufficient(
                    query,
                    f"{_label(event)} amends the provision without supplying a value.",
                    ordered_events=ordered,
                    relationships=relationships,
                )
            current = _merge(current, event.value)
            active = True
        else:
            if event.value is None or not _is_complete(query.attribute, event.value):
                return _insufficient(
                    query,
                    f"{_label(event)} requires a complete replacement value.",
                    ordered_events=ordered,
                    relationships=relationships,
                )
            current = event.value
            active = True

        if active and (current is None or not _is_complete(query.attribute, current)):
            return _insufficient(
                query,
                f"The operative value remains incomplete after {_label(event)}.",
                ordered_events=ordered,
                relationships=relationships,
            )
        chain.append(
            ChainStep(
                source=_label(event),
                operation=event.operation,
                value=current if active else None,
            )
        )

    effective = ordered[-1]
    evidence = _unique_evidence(ordered)
    result = ResolutionResult(
        status=ResolutionStatus.ANSWER,
        attribute=query.attribute,
        subject=query.subject,
        operative_state=OperativeState.ACTIVE if active else OperativeState.DELETED,
        normalized_value=current,
        effective_source=effective.source,
        evidence=evidence,
        amendment_chain=chain,
        reason=(
            f"Applied {len(ordered)} explicitly ordered provision event(s); "
            f"the effective source is {_label(effective)}."
        ),
    )
    return ReductionOutcome(result=result, ordered_events=ordered, relationships=relationships)


def _order_events(
    events: list[ProvisionEvent],
) -> tuple[list[ProvisionEvent], list[ProvisionRelationship], str | None]:
    edges: dict[int, set[int]] = {index: set() for index in range(len(events))}
    relationships: list[ProvisionRelationship] = []

    def add_edge(left: int, right: int, basis: RelationshipBasis) -> None:
        if left == right:
            return
        if right not in edges[left]:
            edges[left].add(right)
        relationship = ProvisionRelationship(
            predecessor=_label(events[left]),
            successor=_label(events[right]),
            basis=basis,
        )
        if relationship not in relationships:
            relationships.append(
                relationship
            )

    label_indexes = {_canonical(_label(event)): index for index, event in enumerate(events)}
    for left in range(len(events)):
        for right in range(left + 1, len(events)):
            first, second = events[left], events[right]
            if first.operation == Operation.BASE and second.operation != Operation.BASE:
                add_edge(left, right, RelationshipBasis.BASE_BEFORE_AMENDMENT)
                continue
            if second.operation == Operation.BASE and first.operation != Operation.BASE:
                add_edge(right, left, RelationshipBasis.BASE_BEFORE_AMENDMENT)
                continue
            first_kind, first_number = _document_number(first)
            second_kind, second_number = _document_number(second)
            if (
                first_kind is not None
                and first_kind == second_kind
                and first_number is not None
                and second_number is not None
                and first_number != second_number
            ):
                if first_number < second_number:
                    add_edge(left, right, RelationshipBasis.DOCUMENT_NUMBER)
                else:
                    add_edge(right, left, RelationshipBasis.DOCUMENT_NUMBER)
                continue
            first_date = first.ordering.effective_date
            second_date = second.ordering.effective_date
            if first_date and second_date and first_date != second_date:
                if first_date < second_date:
                    add_edge(left, right, RelationshipBasis.EFFECTIVE_DATE)
                else:
                    add_edge(right, left, RelationshipBasis.EFFECTIVE_DATE)

    for successor, event in enumerate(events):
        for source in event.ordering.required_sources:
            predecessor = label_indexes.get(_canonical(source))
            if predecessor is not None:
                add_edge(predecessor, successor, RelationshipBasis.EXPLICIT_REFERENCE)
        for source in event.ordering.supersedes:
            predecessor = label_indexes.get(_canonical(source))
            if predecessor is not None:
                add_edge(predecessor, successor, RelationshipBasis.EXPLICIT_SUPERSESSION)

    indegree = {index: 0 for index in range(len(events))}
    for successors in edges.values():
        for successor in successors:
            indegree[successor] += 1

    ordered_indexes: list[int] = []
    remaining = set(range(len(events)))
    while remaining:
        available = sorted(
            (index for index in remaining if indegree[index] == 0),
            key=lambda index: _canonical(_label(events[index])),
        )
        if not available:
            return [], relationships, "The extracted amendment relationships contain a cycle."
        if len(available) > 1 and _has_overlapping_changes([events[index] for index in available]):
            sources = ", ".join(_label(events[index]) for index in available)
            return (
                [],
                relationships,
                f"Precedence is unresolved among provisions that modify the same value: {sources}.",
            )
        for index in available:
            ordered_indexes.append(index)
            remaining.remove(index)
            for successor in edges[index]:
                indegree[successor] -= 1

    return [events[index] for index in ordered_indexes], relationships, None


def _deduplicate(events: list[ProvisionEvent]) -> tuple[list[ProvisionEvent], str | None]:
    unique: dict[str, ProvisionEvent] = {}
    for event in events:
        key = _canonical(_label(event))
        prior = unique.get(key)
        if prior is None:
            unique[key] = event
            continue
        if prior.operation != event.operation or prior.value != event.value:
            return [], f"Conflicting extractions were produced for {_label(event)}."
        merged_evidence = _dedupe_evidence([*prior.evidence, *event.evidence])
        unique[key] = prior.model_copy(update={"evidence": merged_evidence})
    return list(unique.values()), None


def _has_overlapping_changes(events: list[ProvisionEvent]) -> bool:
    seen: set[str] = set()
    for event in events:
        fields = _changed_fields(event)
        if seen.intersection(fields):
            return True
        seen.update(fields)
    return False


def _changed_fields(event: ProvisionEvent) -> set[str]:
    if event.operation == Operation.DELETE or event.value is None:
        return {"amount", "currency", "start", "end"}
    return {
        key
        for key, value in event.value.model_dump().items()
        if value is not None
    }


def _document_number(event: ProvisionEvent) -> tuple[str | None, int | None]:
    label = _label(event)
    match = re.search(r"\b(endorsement|rider)\s*(?:number|no\.?\s*)?(\d+)\b", label, re.I)
    kind = match.group(1).casefold() if match else None
    parsed = int(match.group(2)) if match else None
    return kind, event.ordering.order_number if event.ordering.order_number is not None else parsed


def _merge(current: NormalizedValue | None, update: NormalizedValue) -> NormalizedValue:
    prior = current.model_dump() if current is not None else {
        "amount": None,
        "currency": None,
        "start": None,
        "end": None,
    }
    changes = {key: value for key, value in update.model_dump().items() if value is not None}
    return NormalizedValue(**(prior | changes))


def _is_complete(attribute: Attribute, value: NormalizedValue) -> bool:
    if attribute in {Attribute.LIMIT, Attribute.DEDUCTIBLE}:
        return value.amount is not None and value.currency is not None
    if attribute == Attribute.POLICY_PERIOD:
        return value.start is not None and value.end is not None
    return False


def _label(event: ProvisionEvent) -> str:
    return event.source.provision_label or f"{event.source.document_path} {event.source.locator}"


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _unique_evidence(events: list[ProvisionEvent]) -> list[EvidenceRef]:
    return _dedupe_evidence([evidence for event in events for evidence in event.evidence])


def _dedupe_evidence(evidence: list[EvidenceRef]) -> list[EvidenceRef]:
    unique: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in evidence:
        unique[(item.document_path, item.locator, item.quote)] = item
    return list(unique.values())


def _insufficient(
    query: QuerySpec,
    reason: str,
    *,
    ordered_events: list[ProvisionEvent] | None = None,
    relationships: list[ProvisionRelationship] | None = None,
) -> ReductionOutcome:
    return ReductionOutcome(
        result=ResolutionResult(
            status=ResolutionStatus.INSUFFICIENT_EVIDENCE,
            attribute=query.attribute,
            subject=query.subject,
            operative_state=OperativeState.UNKNOWN,
            normalized_value=None,
            effective_source=None,
            evidence=[],
            amendment_chain=[],
            reason=reason,
        ),
        ordered_events=ordered_events or [],
        relationships=relationships or [],
    )
