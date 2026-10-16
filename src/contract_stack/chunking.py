from __future__ import annotations

import hashlib

from .models import Chunk, TextBlock


def chunk_blocks(
    blocks: list[TextBlock], target_chars: int = 2_400, overlap_blocks: int = 1
) -> list[Chunk]:
    if target_chars <= 0:
        raise ValueError("target_chars must be positive")
    if overlap_blocks < 0:
        raise ValueError("overlap_blocks cannot be negative")

    chunks: list[Chunk] = []
    current: list[TextBlock] = []
    current_chars = 0

    def emit(selected: list[TextBlock]) -> None:
        if not selected:
            return
        text = "\n\n".join(block.text for block in selected)
        locator = _combined_locator(selected)
        digest = hashlib.sha256(
            f"{selected[0].document_path}\0{locator}\0{text}".encode("utf-8")
        ).hexdigest()[:16]
        chunks.append(
            Chunk(
                chunk_id=digest,
                document_path=selected[0].document_path,
                locator=locator,
                text=text,
                extraction_method=_combined_method(selected),
            )
        )

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        emit(current)
        current = current[-overlap_blocks:] if overlap_blocks else []
        current_chars = sum(len(block.text) for block in current)

    for block in blocks:
        # A PDF page is a meaningful evidence boundary. Keep an oversized block
        # intact instead of duplicating it through the overlap buffer.
        if len(block.text) >= target_chars:
            flush()
            current = []
            current_chars = 0
            emit([block])
            continue
        if current and current_chars + len(block.text) > target_chars:
            flush()
        current.append(block)
        current_chars += len(block.text)
    flush()
    return chunks


def _combined_locator(blocks: list[TextBlock]) -> str:
    first, last = blocks[0].locator, blocks[-1].locator
    return first if first == last else f"{first}..{last}"


def _combined_method(blocks: list[TextBlock]):
    methods = {block.extraction_method for block in blocks}
    if len(methods) == 1:
        return blocks[0].extraction_method
    # Mixed chunks can occur only if a PDF combines text and OCR pages. Marking OCR is conservative.
    from .models import ExtractionMethod

    return ExtractionMethod.OCR
