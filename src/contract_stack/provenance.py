from __future__ import annotations

import re

from .models import EvidenceRef, RetrievedChunk


def validate_evidence_provenance(
    evidence: list[EvidenceRef], retrieved: list[RetrievedChunk]
) -> list[str]:
    errors: list[str] = []
    by_source = {
        (item.chunk.document_path, item.chunk.locator): item.chunk.text for item in retrieved
    }
    for index, citation in enumerate(evidence):
        key = (citation.document_path, citation.locator)
        source = by_source.get(key)
        if source is None:
            errors.append(f"evidence[{index}] does not identify a retrieved chunk")
            continue
        if _normalize(citation.quote) not in _normalize(source):
            errors.append(f"evidence[{index}] quote is not traceable to the retrieved chunk")
    return errors


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()
