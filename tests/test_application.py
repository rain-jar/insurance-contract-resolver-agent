from pathlib import Path

import pytest

from contract_stack.application import (
    AnalysisDocument,
    AnalysisInputError,
    AnalysisLimits,
    ContractAnalysisService,
)
from contract_stack.generation import StructuredGeneration
from contract_stack.ingestion import DocumentIngestor
from contract_stack.models import (
    Attribute,
    EvidenceRef,
    ExtractionMethod,
    NormalizedValue,
    Operation,
    OrderingInfo,
    ProvisionEvent,
    ProvisionExtraction,
    ResolutionStatus,
    SourceRef,
)
from contract_stack.relationship_retrieval import RelationshipDrivenResolver
from contract_stack.retrieval import HybridRetriever


class _FakeGenerator:
    def __init__(self, outputs: list[ProvisionExtraction]) -> None:
        self.outputs = outputs
        self.calls = 0

    def generate(self, **_: object) -> StructuredGeneration:
        output = self.outputs[self.calls]
        self.calls += 1
        return StructuredGeneration(
            output=output,
            metadata={
                "requested_model": "fake-production-test-model",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        )


def test_analysis_service_runs_auditable_relationship_resolution(tmp_path: Path) -> None:
    source = tmp_path / "uploaded.txt"
    source.write_text(
        "Base declarations set the On Premises limit to USD 3,500,000. "
        "Endorsement 8 replaces the On Premises limit with USD 5,000,000.",
        encoding="utf-8",
    )
    events = [
        _event(
            "Base declarations Item 2",
            Operation.BASE,
            3_500_000,
            "Base declarations set the On Premises limit to USD 3,500,000.",
        ),
        _event(
            "Endorsement 8",
            Operation.REPLACE,
            5_000_000,
            "Endorsement 8 replaces the On Premises limit with USD 5,000,000.",
            number=8,
        ),
    ]
    generator = _FakeGenerator([ProvisionExtraction(events=events)])
    service = _service(generator)

    analysis = service.analyze(
        "What is the current On Premises limit?",
        [AnalysisDocument(source_path=source, display_name="contract.txt")],
    )

    assert analysis.run.result.status == ResolutionStatus.ANSWER
    assert analysis.run.result.normalized_value == NormalizedValue(
        amount=5_000_000,
        currency="USD",
        start=None,
        end=None,
    )
    assert analysis.documents[0].display_name == "contract.txt"
    assert analysis.documents[0].byte_size == source.stat().st_size
    assert len(analysis.documents[0].sha256) == 64
    assert analysis.audit.generation_call_count == 1
    assert len(analysis.audit.initial_retrieved_chunk_ids) == 1
    assert not analysis.audit.expansion_triggered
    assert analysis.result_provenance_errors == []
    assert generator.calls == 1


def test_unsupported_question_uses_no_generation_call(tmp_path: Path) -> None:
    source = tmp_path / "contract.txt"
    source.write_text("Territorial terms apply in Canada.", encoding="utf-8")
    generator = _FakeGenerator([])

    analysis = _service(generator).analyze(
        "What territory is covered?",
        [AnalysisDocument(source_path=source, display_name="contract.txt")],
    )

    assert analysis.run.result.status == ResolutionStatus.UNSUPPORTED_ATTRIBUTE
    assert analysis.audit.generation_call_count == 0
    assert analysis.audit.initial_retrieved_chunk_ids == []
    assert generator.calls == 0


def test_analysis_service_rejects_unsafe_display_names(tmp_path: Path) -> None:
    source = tmp_path / "contract.txt"
    source.write_text("A valid non-empty document.", encoding="utf-8")

    with pytest.raises(AnalysisInputError, match="plain filenames"):
        _service(_FakeGenerator([])).analyze(
            "What is the current limit?",
            [AnalysisDocument(source_path=source, display_name="../contract.txt")],
        )


def test_analysis_service_enforces_document_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "contract.txt"
    source.write_text("This document is too large.", encoding="utf-8")
    service = _service(
        _FakeGenerator([]), AnalysisLimits(max_document_bytes=5)
    )

    with pytest.raises(AnalysisInputError, match="exceeds"):
        service.analyze(
            "What is the current limit?",
            [AnalysisDocument(source_path=source, display_name="contract.txt")],
        )


def _service(
    generator: _FakeGenerator, limits: AnalysisLimits | None = None
) -> ContractAnalysisService:
    return ContractAnalysisService(
        ingestor=DocumentIngestor(),
        retriever=HybridRetriever(),
        resolver=RelationshipDrivenResolver(generator),
        limits=limits,
    )


def _event(
    label: str,
    operation: Operation,
    amount: int,
    quote: str,
    *,
    number: int | None = None,
) -> ProvisionEvent:
    return ProvisionEvent(
        attribute=Attribute.LIMIT,
        subject="On Premises",
        operation=operation,
        value=NormalizedValue(
            amount=amount,
            currency="USD",
            start=None,
            end=None,
        ),
        source=SourceRef(
            document_path="contract.txt",
            provision_label=label,
            locator="paragraph:1",
        ),
        evidence=[
            EvidenceRef(
                document_path="contract.txt",
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
