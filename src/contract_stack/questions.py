from __future__ import annotations

import re

from .models import Attribute, QuerySpec


def interpret_question(question: str) -> QuerySpec:
    """Interpret benchmark-v1's narrow ontology without forcing unsupported questions."""
    lowered = " ".join(question.lower().split())
    if "deductible" in lowered:
        attribute = Attribute.DEDUCTIBLE
        subject = _subject_before(lowered, "deductible")
    elif "limit" in lowered:
        attribute = Attribute.LIMIT
        subject = _subject_before(lowered, "limit")
    elif "policy period" in lowered or "bond period" in lowered:
        attribute = Attribute.POLICY_PERIOD
        subject = "Bond Period"
    else:
        return QuerySpec(attribute=Attribute.UNSUPPORTED, subject=None)
    return QuerySpec(attribute=attribute, subject=subject)


def _subject_before(question: str, marker: str) -> str | None:
    prefix = question.split(marker, 1)[0]
    prefix = re.sub(r"^(what|which)\s+is\s+the\s+(currently\s+)?(operative\s+|current\s+)?", "", prefix)
    prefix = re.sub(r"\bsingle\s+loss\s*$", "", prefix).strip(" ?")
    return " ".join(word.capitalize() for word in prefix.split()) or None
