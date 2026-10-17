from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, Protocol, TypeVar

from openai import OpenAI
from pydantic import BaseModel


GENERATION_MODEL = "gpt-6.1-sol"
REASONING_EFFORT = "medium"
REASONING_MODE = "standard"
SERVICE_TIER = "default"
MAX_OUTPUT_TOKENS = 25_000

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class StructuredGeneration(Generic[ModelT]):
    output: ModelT
    metadata: dict[str, Any]


class StructuredGenerator(Protocol):
    def generate(
        self,
        *,
        instructions: str,
        prompt: str,
        response_model: type[ModelT],
    ) -> StructuredGeneration[ModelT]: ...


class OpenAIStructuredGenerator:
    """The sole production adapter for structured OpenAI generation calls."""

    def __init__(self, client: OpenAI) -> None:
        self.client = client

    def generate(
        self,
        *,
        instructions: str,
        prompt: str,
        response_model: type[ModelT],
    ) -> StructuredGeneration[ModelT]:
        response = self.client.responses.parse(
            model=GENERATION_MODEL,
            instructions=instructions,
            input=prompt,
            reasoning={"effort": REASONING_EFFORT, "mode": REASONING_MODE},
            service_tier=SERVICE_TIER,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            text_format=response_model,
        )
        if response.output_parsed is None:
            raise RuntimeError("The model response did not contain parsed structured output")
        usage = response.usage.model_dump(mode="json") if response.usage is not None else None
        return StructuredGeneration(
            output=response.output_parsed,
            metadata={
                "response_id": response.id,
                "requested_model": GENERATION_MODEL,
                "response_model": response.model,
                "reasoning_effort": REASONING_EFFORT,
                "reasoning_mode": REASONING_MODE,
                "requested_service_tier": SERVICE_TIER,
                "response_service_tier": response.service_tier,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "completed_at_utc": datetime.now(UTC).isoformat(),
                "usage": usage,
            },
        )


def as_structured_generator(value: StructuredGenerator | OpenAI) -> StructuredGenerator:
    """Accept an injected generator while preserving the existing OpenAI-client API."""
    if hasattr(value, "generate"):
        return value
    return OpenAIStructuredGenerator(value)
