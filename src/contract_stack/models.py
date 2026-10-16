from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Attribute(StrEnum):
    LIMIT = "LIMIT"
    DEDUCTIBLE = "DEDUCTIBLE"
    POLICY_PERIOD = "POLICY_PERIOD"
    UNSUPPORTED = "UNSUPPORTED"


class ResolutionStatus(StrEnum):
    ANSWER = "ANSWER"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED_ATTRIBUTE = "UNSUPPORTED_ATTRIBUTE"
    PROCESSING_ERROR = "PROCESSING_ERROR"


class OperativeState(StrEnum):
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"
    UNKNOWN = "UNKNOWN"


class ExtractionMethod(StrEnum):
    TEXT = "TEXT"
    HTML = "HTML"
    OCR = "OCR"


class Operation(StrEnum):
    BASE = "BASE"
    ADD = "ADD"
    AMEND = "AMEND"
    REPLACE = "REPLACE"
    DELETE_AND_RESTATE = "DELETE_AND_RESTATE"
    DELETE = "DELETE"
    SUPERSEDE = "SUPERSEDE"


class RelationshipBasis(StrEnum):
    BASE_BEFORE_AMENDMENT = "BASE_BEFORE_AMENDMENT"
    DOCUMENT_NUMBER = "DOCUMENT_NUMBER"
    EFFECTIVE_DATE = "EFFECTIVE_DATE"
    EXPLICIT_REFERENCE = "EXPLICIT_REFERENCE"
    EXPLICIT_SUPERSESSION = "EXPLICIT_SUPERSESSION"


class NormalizedValue(StrictModel):
    amount: int | None = Field(description="Whole currency units for LIMIT or DEDUCTIBLE")
    currency: str | None = Field(description="ISO currency code when amount is present")
    start: str | None = Field(description="ISO-8601 local datetime for POLICY_PERIOD start")
    end: str | None = Field(description="ISO-8601 local datetime for POLICY_PERIOD end")


class SourceRef(StrictModel):
    document_path: str
    provision_label: str | None
    locator: str


class EvidenceRef(StrictModel):
    document_path: str
    locator: str
    quote: str
    extraction_method: ExtractionMethod


class OrderingInfo(StrictModel):
    order_number: int | None = Field(
        description="Numeric endorsement or rider number, when explicitly present"
    )
    effective_date: str | None = Field(
        description="ISO-8601 effective date, when explicitly present"
    )
    required_sources: list[str] = Field(
        description="Sources or schedules explicitly required to determine this event's value"
    )
    supersedes: list[str] = Field(
        description="Earlier source labels this event explicitly supersedes"
    )


class ProvisionEvent(StrictModel):
    attribute: Attribute
    subject: str | None
    operation: Operation
    value: NormalizedValue | None
    source: SourceRef
    evidence: list[EvidenceRef]
    ordering: OrderingInfo


class ProvisionExtraction(StrictModel):
    events: list[ProvisionEvent]


class ProvisionRelationship(StrictModel):
    predecessor: str
    successor: str
    basis: RelationshipBasis


class ChainStep(StrictModel):
    source: str
    operation: Operation
    value: NormalizedValue | None


class ResolutionResult(StrictModel):
    status: ResolutionStatus
    attribute: Attribute
    subject: str | None
    operative_state: OperativeState
    normalized_value: NormalizedValue | None
    effective_source: SourceRef | None
    evidence: list[EvidenceRef]
    amendment_chain: list[ChainStep]
    reason: str

    @model_validator(mode="after")
    def validate_status_consistency(self) -> "ResolutionResult":
        if self.status == ResolutionStatus.ANSWER:
            if self.operative_state == OperativeState.ACTIVE and self.normalized_value is None:
                raise ValueError("An active ANSWER requires normalized_value")
            if self.operative_state == OperativeState.UNKNOWN:
                raise ValueError("An ANSWER cannot have UNKNOWN operative state")
            if self.effective_source is None:
                raise ValueError("An ANSWER requires effective_source")
            if not self.evidence:
                raise ValueError("An ANSWER requires supporting evidence")
        elif self.normalized_value is not None:
            raise ValueError("Non-answer results cannot contain normalized_value")
        elif self.operative_state != OperativeState.UNKNOWN:
            raise ValueError("Non-answer results must have UNKNOWN operative state")
        return self


class QuerySpec(StrictModel):
    attribute: Attribute
    subject: str | None


class TextBlock(StrictModel):
    document_path: str
    block_index: int
    locator: str
    text: str
    extraction_method: ExtractionMethod
    page_number: int | None = None


class Chunk(StrictModel):
    chunk_id: str
    document_path: str
    locator: str
    text: str
    extraction_method: ExtractionMethod


class RetrievedChunk(StrictModel):
    chunk: Chunk
    score: float
    rank: int
