from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from .models import (
    Attribute,
    Chunk,
    NormalizedValue,
    Operation,
    OperativeState,
    ProvisionEvent,
    ProvisionRelationship,
    QuerySpec,
    ResolutionResult,
    ResolutionStatus,
    RetrievedChunk,
)
from .questions import interpret_question
from .reducer import reduce_provisions
from .resolver import ContractStackResolver, ResolverRun
from .retrieval import HybridRetriever


@dataclass(frozen=True)
class RelationshipExpansion:
    triggered: bool
    reasons: list[str]
    query: str | None
    added: list[RetrievedChunk]


@dataclass(frozen=True)
class RelationshipResolverRun:
    result: ResolutionResult
    initial_run: ResolverRun
    expansion: RelationshipExpansion
    expansion_events: list[ProvisionEvent]
    combined_events: list[ProvisionEvent]
    ordered_events: list[ProvisionEvent]
    relationships: list[ProvisionRelationship]
    expansion_provenance_errors: list[str]
    expansion_api_metadata: dict[str, Any] | None


class BoundedRelationshipRetriever:
    def __init__(self, max_added_chunks: int = 2) -> None:
        if max_added_chunks < 0:
            raise ValueError("max_added_chunks cannot be negative")
        self.max_added_chunks = max_added_chunks

    def expand(
        self,
        query: QuerySpec,
        chunks: list[Chunk],
        initial: list[RetrievedChunk],
        events: list[ProvisionEvent],
    ) -> RelationshipExpansion:
        if query.attribute == Attribute.UNSUPPORTED or self.max_added_chunks == 0:
            return RelationshipExpansion(False, [], None, [])

        events = [event for event in events if event.attribute == query.attribute]

        labels = {_canonical(_label(event)) for event in events}
        missing_sources = sorted(
            {
                source
                for event in events
                for source in [*event.ordering.required_sources, *event.ordering.supersedes]
                if _canonical(source) not in labels
            }
        )
        numbered_events = [
            (event, item)
            for event in events
            if (item := _document_number(event)) is not None
        ]
        predecessor_bounds: dict[str, int] = {}
        base_paths = {
            event.source.document_path.replace("\\", "/").casefold()
            for event in events
            if event.operation == Operation.BASE
        }
        if base_paths:
            earliest_by_kind: dict[str, tuple[ProvisionEvent, int]] = {}
            for event, (kind, number) in numbered_events:
                prior = earliest_by_kind.get(kind)
                if prior is None or number < prior[1]:
                    earliest_by_kind[kind] = (event, number)
            for kind, (event, number) in earliest_by_kind.items():
                event_path = event.source.document_path.replace("\\", "/").casefold()
                if event_path not in base_paths:
                    predecessor_bounds[kind] = number

        partial_amendment = any(
            event.operation == Operation.AMEND
            and event.value is not None
            and not _is_complete(query.attribute, event.value)
            for event in events
        )
        reasons: list[str] = []
        if missing_sources:
            reasons.append("MISSING_EXPLICIT_SOURCE")
        if predecessor_bounds:
            reasons.append("POSSIBLE_MISSING_PREDECESSOR")
        if partial_amendment and (missing_sources or predecessor_bounds):
            reasons.append("PARTIAL_AMENDMENT_REQUIRES_PRIOR_STATE")
        if not reasons:
            return RelationshipExpansion(False, [], None, [])

        initial_ids = {item.chunk.chunk_id for item in initial}
        candidate_relations = [
            (chunk, *_candidate_relation(chunk.text, query, missing_sources, predecessor_bounds))
            for chunk in chunks
            if chunk.chunk_id not in initial_ids
        ]
        predecessor_distances = [
            distance
            for _, _, distance in candidate_relations
            if distance is not None
        ]
        closest_predecessor = min(predecessor_distances) if predecessor_distances else None
        candidates = [
            chunk
            for chunk, explicit_match, distance in candidate_relations
            if explicit_match
            or (closest_predecessor is not None and distance == closest_predecessor)
        ]
        expansion_query = _expansion_query(
            query,
            missing_sources=missing_sources,
            predecessor_bounds=predecessor_bounds,
        )
        ranked = HybridRetriever().retrieve(
            expansion_query, candidates, top_k=self.max_added_chunks
        )
        added = [
            item.model_copy(update={"rank": len(initial) + index})
            for index, item in enumerate(ranked, start=1)
        ]
        return RelationshipExpansion(True, reasons, expansion_query, added)


class RelationshipDrivenResolver:
    def __init__(self, client: OpenAI, *, max_added_chunks: int = 2) -> None:
        self.base_resolver = ContractStackResolver(client)
        self.expander = BoundedRelationshipRetriever(max_added_chunks=max_added_chunks)

    def resolve_from_initial(
        self,
        question: str,
        chunks: list[Chunk],
        initial_retrieved: list[RetrievedChunk],
        initial_run: ResolverRun,
    ) -> RelationshipResolverRun:
        query = interpret_question(question)
        if initial_run.extraction_provenance_errors:
            return _unchanged(initial_run, RelationshipExpansion(False, [], None, []))

        expansion = self.expander.expand(
            query, chunks, initial_retrieved, initial_run.extracted_events
        )
        if not expansion.added:
            return _unchanged(initial_run, expansion)

        extraction = self.base_resolver.extract(question, expansion.added)
        if extraction.provenance_errors:
            result = ResolutionResult(
                status=ResolutionStatus.INSUFFICIENT_EVIDENCE,
                attribute=query.attribute,
                subject=query.subject,
                operative_state=OperativeState.UNKNOWN,
                normalized_value=None,
                effective_source=None,
                evidence=[],
                amendment_chain=[],
                reason="Relationship-expansion evidence failed provenance validation.",
            )
            return RelationshipResolverRun(
                result=result,
                initial_run=initial_run,
                expansion=expansion,
                expansion_events=extraction.events,
                combined_events=[*initial_run.extracted_events, *extraction.events],
                ordered_events=[],
                relationships=[],
                expansion_provenance_errors=extraction.provenance_errors,
                expansion_api_metadata=extraction.api_metadata,
            )

        combined_events = [*initial_run.extracted_events, *extraction.events]
        reduction = reduce_provisions(query, combined_events)
        return RelationshipResolverRun(
            result=reduction.result,
            initial_run=initial_run,
            expansion=expansion,
            expansion_events=extraction.events,
            combined_events=combined_events,
            ordered_events=reduction.ordered_events,
            relationships=reduction.relationships,
            expansion_provenance_errors=[],
            expansion_api_metadata=extraction.api_metadata,
        )


def _unchanged(
    initial_run: ResolverRun, expansion: RelationshipExpansion
) -> RelationshipResolverRun:
    return RelationshipResolverRun(
        result=initial_run.result,
        initial_run=initial_run,
        expansion=expansion,
        expansion_events=[],
        combined_events=initial_run.extracted_events,
        ordered_events=initial_run.ordered_events,
        relationships=initial_run.relationships,
        expansion_provenance_errors=[],
        expansion_api_metadata=None,
    )


def _candidate_relation(
    text: str,
    query: QuerySpec,
    missing_sources: list[str],
    predecessor_bounds: dict[str, int],
) -> tuple[bool, int | None]:
    explicit_match = _attribute_matches(query, text) and any(
        _source_mentioned(source, text) for source in missing_sources
    )
    if not _attribute_matches(query, text) or not _contains_amendment_language(text):
        return explicit_match, None
    distances: list[int] = []
    for kind, bound in predecessor_bounds.items():
        numbers = _numbers_in_text(kind, text)
        distances.extend(bound - number for number in numbers if number < bound)
    return explicit_match, min(distances) if distances else None


def _attribute_matches(query: QuerySpec, text: str) -> bool:
    lowered = _canonical(text)
    if query.attribute == Attribute.POLICY_PERIOD:
        return bool(
            re.search(
                r"\bitem 2\b.{0,160}\b(?:bond|policy) period\b.{0,200}"
                r"\b(?:amend\w*|replac\w*|restat\w*|supersed\w*)\b"
                r"|\b(?:amend\w*|replac\w*|restat\w*|supersed\w*)\b.{0,200}"
                r"\bitem 2\b.{0,160}\b(?:bond|policy) period\b",
                lowered,
                re.I | re.S,
            )
        )
    attribute_term = "deductible" if query.attribute == Attribute.DEDUCTIBLE else "limit"
    subject_terms = [term for term in _canonical(query.subject or "").split() if len(term) > 2]
    return attribute_term in lowered and all(term in lowered for term in subject_terms)


def _contains_amendment_language(text: str) -> bool:
    return bool(re.search(r"\b(amend\w*|replac\w*|restat\w*|supersed\w*|delet\w*)\b", text, re.I))


def _source_mentioned(source: str, text: str) -> bool:
    source_number = re.search(
        r"\b(endorsement|rider)\s*(?:number|no\.?\s*)?(\d+)\b", source, re.I
    )
    if source_number:
        kind, number = source_number.group(1), source_number.group(2)
        return bool(
            re.search(
                rf"\b{re.escape(kind)}\s*(?:number|no\.?\s*)?{number}\b",
                text,
                re.I,
            )
        )
    lowered = _canonical(text)
    canonical_source = _canonical(source)
    return bool(canonical_source) and canonical_source in lowered


def _expansion_query(
    query: QuerySpec,
    *,
    missing_sources: list[str],
    predecessor_bounds: dict[str, int],
) -> str:
    parts = [query.subject or query.attribute.value, query.attribute.value]
    parts.extend(missing_sources)
    parts.extend(predecessor_bounds)
    parts.extend(["amended", "replaced", "superseded", "prior operative provision"])
    return " ".join(parts)


def _document_number(event: ProvisionEvent) -> tuple[str, int] | None:
    label = _label(event)
    match = re.search(r"\b(endorsement|rider)\s*(?:number|no\.?\s*)?(\d+)\b", label, re.I)
    if match is None and event.ordering.order_number is None:
        return None
    kind = match.group(1).casefold() if match else "amendment"
    number = (
        event.ordering.order_number
        if event.ordering.order_number is not None
        else int(match.group(2))
    )
    return kind, number


def _numbers_in_text(kind: str, text: str) -> list[int]:
    return [
        int(match.group(1))
        for match in re.finditer(
            rf"\b{re.escape(kind)}\s*(?:number|no\.?\s*)?(\d+)\b", text, re.I
        )
    ]


def _is_complete(attribute: Attribute, value: NormalizedValue) -> bool:
    if attribute in {Attribute.LIMIT, Attribute.DEDUCTIBLE}:
        return value.amount is not None and value.currency is not None
    if attribute == Attribute.POLICY_PERIOD:
        return value.start is not None and value.end is not None
    return False


def _label(event: ProvisionEvent) -> str:
    return event.source.provision_label or event.source.document_path


def _canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
