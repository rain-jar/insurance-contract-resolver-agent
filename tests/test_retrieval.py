from contract_stack.models import Chunk, ExtractionMethod
from contract_stack.retrieval import HybridRetriever


def test_lexical_retrieval_ranks_relevant_clause_first() -> None:
    chunks = [
        Chunk(chunk_id="noise", document_path="a", locator="p1", text="Mailing address is amended.", extraction_method=ExtractionMethod.TEXT),
        Chunk(chunk_id="limit", document_path="a", locator="p2", text="On Premises single loss limit is USD 5,000,000.", extraction_method=ExtractionMethod.TEXT),
    ]
    results = HybridRetriever().retrieve("current On Premises single loss limit", chunks, top_k=2)
    assert results[0].chunk.chunk_id == "limit"
