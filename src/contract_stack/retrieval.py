from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Protocol

from openai import OpenAI
from rank_bm25 import BM25Plus

from .models import Chunk, RetrievedChunk


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, client: OpenAI, model: str, cache_dir: Path | None = None) -> None:
        self.client = client
        self.model = model
        self.cache_dir = cache_dir
        self.last_metadata: dict[str, Any] | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = [None] * len(texts)
        missing_indexes: list[int] = []
        missing_texts: list[str] = []
        for index, text in enumerate(texts):
            cached = self._read(text)
            if cached is None:
                missing_indexes.append(index)
                missing_texts.append(text)
            else:
                results[index] = cached
        response_model = self.model
        usage = None
        if missing_texts:
            response = self.client.embeddings.create(model=self.model, input=missing_texts)
            response_model = response.model
            usage = response.usage.model_dump(mode="json") if response.usage else None
            for index, item in zip(missing_indexes, response.data, strict=True):
                vector = list(item.embedding)
                results[index] = vector
                self._write(texts[index], vector)
        self.last_metadata = {
            "requested_model": self.model,
            "response_model": response_model,
            "input_count": len(texts),
            "cache_hit_count": len(texts) - len(missing_texts),
            "api_input_count": len(missing_texts),
            "usage": usage,
        }
        return [vector for vector in results if vector is not None]

    def _path(self, text: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(f"{self.model}\0{text}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read(self, text: str) -> list[float] | None:
        path = self._path(text)
        if path is None or not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, text: str, vector: list[float]) -> None:
        path = self._path(text)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(vector), encoding="utf-8")


class HybridRetriever:
    def __init__(self, embedder: Embedder | None = None, rrf_k: int = 60) -> None:
        self.embedder = embedder
        self.rrf_k = rrf_k

    def retrieve(self, question: str, chunks: list[Chunk], top_k: int = 8) -> list[RetrievedChunk]:
        if not chunks or top_k <= 0:
            return []
        tokenized = [_tokens(chunk.text) for chunk in chunks]
        # BM25+ avoids the zero/negative-IDF edge case that BM25Okapi exhibits
        # on the very small contract stacks used by this benchmark.
        bm25 = BM25Plus(tokenized)
        lexical_scores = bm25.get_scores(_tokens(question))
        lexical_order = sorted(range(len(chunks)), key=lambda i: lexical_scores[i], reverse=True)

        rank_scores = {index: 1.0 / (self.rrf_k + rank) for rank, index in enumerate(lexical_order, 1)}
        if self.embedder is not None:
            vectors = self.embedder.embed([question, *[chunk.text for chunk in chunks]])
            query_vector, chunk_vectors = vectors[0], vectors[1:]
            semantic_order = sorted(
                range(len(chunks)),
                key=lambda i: _cosine(query_vector, chunk_vectors[i]),
                reverse=True,
            )
            for rank, index in enumerate(semantic_order, 1):
                rank_scores[index] += 1.0 / (self.rrf_k + rank)

        ordered = sorted(range(len(chunks)), key=lambda i: rank_scores[i], reverse=True)[:top_k]
        return [
            RetrievedChunk(chunk=chunks[index], score=rank_scores[index], rank=rank)
            for rank, index in enumerate(ordered, 1)
        ]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
