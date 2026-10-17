from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .chunking import chunk_blocks
from .ingestion import DocumentIngestor
from .models import Attribute, Chunk, RetrievedChunk
from .questions import interpret_question
from .provenance import validate_evidence_provenance
from .relationship_retrieval import RelationshipDrivenResolver, RelationshipResolverRun
from .retrieval import HybridRetriever


SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".pdf", ".html", ".htm", ".txt"})


class AnalysisInputError(ValueError):
    pass


@dataclass(frozen=True)
class AnalysisLimits:
    max_documents: int = 50
    max_document_bytes: int = 25 * 1024 * 1024
    max_stack_bytes: int = 100 * 1024 * 1024
    max_question_characters: int = 2_000
    top_k: int = 8

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True)
class AnalysisDocument:
    source_path: Path
    display_name: str


@dataclass(frozen=True)
class DocumentManifestEntry:
    display_name: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class AnalysisAudit:
    started_at_utc: str
    completed_at_utc: str
    elapsed_seconds: float
    top_k: int
    initial_retrieved_chunk_ids: list[str]
    expansion_triggered: bool
    expansion_reasons: list[str]
    expansion_chunk_ids: list[str]
    generation_call_count: int
    embedding_metadata: dict[str, Any] | None


@dataclass(frozen=True)
class ContractAnalysis:
    run: RelationshipResolverRun
    documents: list[DocumentManifestEntry]
    audit: AnalysisAudit
    result_provenance_errors: list[str]


class ContractAnalysisService:
    """Application orchestration around the validated relationship resolver."""

    def __init__(
        self,
        *,
        ingestor: DocumentIngestor,
        retriever: HybridRetriever,
        resolver: RelationshipDrivenResolver,
        limits: AnalysisLimits | None = None,
    ) -> None:
        self.ingestor = ingestor
        self.retriever = retriever
        self.resolver = resolver
        self.limits = limits or AnalysisLimits()

    def analyze(
        self, question: str, documents: list[AnalysisDocument]
    ) -> ContractAnalysis:
        started_at = datetime.now(UTC)
        started = time.monotonic()
        clean_question = _validate_question(question, self.limits)
        manifests = _validate_documents(documents, self.limits)
        chunks = self._ingest(documents)

        query = interpret_question(clean_question)
        initial_retrieved: list[RetrievedChunk]
        if query.attribute == Attribute.UNSUPPORTED:
            initial_retrieved = []
        else:
            initial_retrieved = self.retriever.retrieve(
                clean_question, chunks, top_k=self.limits.top_k
            )
        run = self.resolver.resolve(clean_question, chunks, initial_retrieved)
        supplied_evidence = [*initial_retrieved, *run.expansion.added]
        result_provenance_errors = validate_evidence_provenance(
            run.result.evidence, supplied_evidence
        )
        completed_at = datetime.now(UTC)
        generation_call_count = sum(
            metadata is not None
            for metadata in (
                run.initial_run.api_metadata,
                run.expansion_api_metadata,
            )
        )
        return ContractAnalysis(
            run=run,
            documents=manifests,
            result_provenance_errors=result_provenance_errors,
            audit=AnalysisAudit(
                started_at_utc=started_at.isoformat(),
                completed_at_utc=completed_at.isoformat(),
                elapsed_seconds=round(time.monotonic() - started, 6),
                top_k=self.limits.top_k,
                initial_retrieved_chunk_ids=[
                    item.chunk.chunk_id for item in initial_retrieved
                ],
                expansion_triggered=run.expansion.triggered,
                expansion_reasons=run.expansion.reasons,
                expansion_chunk_ids=[
                    item.chunk.chunk_id for item in run.expansion.added
                ],
                generation_call_count=generation_call_count,
                embedding_metadata=getattr(
                    self.retriever.embedder, "last_metadata", None
                ),
            ),
        )

    def _ingest(self, documents: list[AnalysisDocument]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for document in documents:
            blocks = self.ingestor.ingest(
                document.source_path, display_path=document.display_name
            )
            chunks.extend(chunk_blocks(blocks))
        return chunks


def _validate_question(question: str, limits: AnalysisLimits) -> str:
    clean = question.strip()
    if not clean:
        raise AnalysisInputError("A question is required.")
    if len(clean) > limits.max_question_characters:
        raise AnalysisInputError(
            f"The question exceeds {limits.max_question_characters} characters."
        )
    return clean


def _validate_documents(
    documents: list[AnalysisDocument], limits: AnalysisLimits
) -> list[DocumentManifestEntry]:
    if not documents:
        raise AnalysisInputError("At least one contract document is required.")
    if len(documents) > limits.max_documents:
        raise AnalysisInputError(
            f"A contract stack may contain at most {limits.max_documents} documents."
        )

    names: set[str] = set()
    total_bytes = 0
    manifests: list[DocumentManifestEntry] = []
    for document in documents:
        source_path = document.source_path
        display_name = document.display_name.strip()
        if not display_name or Path(display_name).name != display_name:
            raise AnalysisInputError("Document display names must be plain filenames.")
        canonical_name = display_name.casefold()
        if canonical_name in names:
            raise AnalysisInputError(f"Duplicate document name: {display_name}")
        names.add(canonical_name)
        if Path(display_name).suffix.casefold() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise AnalysisInputError(f"Unsupported document format: {display_name}")
        if not source_path.is_file():
            raise AnalysisInputError(f"Document is not a readable file: {display_name}")

        byte_size = source_path.stat().st_size
        if byte_size == 0:
            raise AnalysisInputError(f"Document is empty: {display_name}")
        if byte_size > limits.max_document_bytes:
            raise AnalysisInputError(
                f"Document exceeds the {limits.max_document_bytes}-byte limit: {display_name}"
            )
        total_bytes += byte_size
        if total_bytes > limits.max_stack_bytes:
            raise AnalysisInputError(
                f"Contract stack exceeds the {limits.max_stack_bytes}-byte limit."
            )
        manifests.append(
            DocumentManifestEntry(
                display_name=display_name,
                byte_size=byte_size,
                sha256=_sha256_file(source_path),
            )
        )
    return manifests


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
