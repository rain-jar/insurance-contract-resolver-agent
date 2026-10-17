from types import SimpleNamespace

from contract_stack.models import Chunk, ExtractionMethod
from contract_stack.retrieval import HybridRetriever, OpenAIEmbedder


def test_lexical_retrieval_ranks_relevant_clause_first() -> None:
    chunks = [
        Chunk(chunk_id="noise", document_path="a", locator="p1", text="Mailing address is amended.", extraction_method=ExtractionMethod.TEXT),
        Chunk(chunk_id="limit", document_path="a", locator="p2", text="On Premises single loss limit is USD 5,000,000.", extraction_method=ExtractionMethod.TEXT),
    ]
    results = HybridRetriever().retrieve("current On Premises single loss limit", chunks, top_k=2)
    assert results[0].chunk.chunk_id == "limit"


def test_openai_embedder_records_usage_and_cache_behavior(tmp_path) -> None:
    usage = SimpleNamespace(
        model_dump=lambda **_: {"prompt_tokens": 4, "total_tokens": 4}
    )
    response = SimpleNamespace(
        model="text-embedding-test",
        usage=usage,
        data=[SimpleNamespace(embedding=[1.0, 0.0])],
    )
    embeddings = SimpleNamespace(create=lambda **_: response)
    embedder = OpenAIEmbedder(
        SimpleNamespace(embeddings=embeddings),
        "text-embedding-test",
        cache_dir=tmp_path,
    )

    assert embedder.embed(["example"]) == [[1.0, 0.0]]
    assert embedder.last_metadata == {
        "requested_model": "text-embedding-test",
        "response_model": "text-embedding-test",
        "input_count": 1,
        "cache_hit_count": 0,
        "api_input_count": 1,
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }

    assert embedder.embed(["example"]) == [[1.0, 0.0]]
    assert embedder.last_metadata["cache_hit_count"] == 1
    assert embedder.last_metadata["api_input_count"] == 0
    assert embedder.last_metadata["usage"] is None
