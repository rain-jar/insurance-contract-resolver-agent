from __future__ import annotations

from pathlib import Path

from .chunking import chunk_blocks
from .ingestion import DocumentIngestor
from .models import Chunk


def ingest_stack(
    benchmark_root: Path,
    contract_stack: list[str],
    ingestor: DocumentIngestor,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for relative_path in contract_stack:
        path = benchmark_root / relative_path
        blocks = ingestor.ingest(path, display_path=relative_path)
        chunks.extend(chunk_blocks(blocks))
    return chunks
