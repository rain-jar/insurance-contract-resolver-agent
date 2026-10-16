from contract_stack.models import Chunk, EvidenceRef, ExtractionMethod, RetrievedChunk
from contract_stack.provenance import validate_evidence_provenance


def test_provenance_accepts_traceable_quote() -> None:
    chunk = Chunk(chunk_id="c", document_path="a.txt", locator="paragraph:1", text="Limit is USD 5,000,000.", extraction_method=ExtractionMethod.TEXT)
    retrieved = [RetrievedChunk(chunk=chunk, score=1.0, rank=1)]
    evidence = [EvidenceRef(document_path="a.txt", locator="paragraph:1", quote="USD 5,000,000", extraction_method=ExtractionMethod.TEXT)]
    assert validate_evidence_provenance(evidence, retrieved) == []


def test_provenance_rejects_invented_quote() -> None:
    chunk = Chunk(chunk_id="c", document_path="a.txt", locator="paragraph:1", text="Limit is USD 5,000,000.", extraction_method=ExtractionMethod.TEXT)
    retrieved = [RetrievedChunk(chunk=chunk, score=1.0, rank=1)]
    evidence = [EvidenceRef(document_path="a.txt", locator="paragraph:1", quote="USD 6,000,000", extraction_method=ExtractionMethod.TEXT)]
    assert validate_evidence_provenance(evidence, retrieved)
