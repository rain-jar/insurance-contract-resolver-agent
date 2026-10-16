from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from .baseline import (
    BASELINE_INSTRUCTIONS,
    GENERATION_MODEL,
    MAX_OUTPUT_TOKENS,
    REASONING_EFFORT,
    REASONING_MODE,
    SERVICE_TIER,
    DirectRAGBaseline,
)
from .evaluation import amendment_chain_correct, abstention_correct, operative_state_correct
from .ingestion import DocumentIngestor
from .models import ResolutionStatus
from .pipeline import ingest_stack
from .provenance import validate_evidence_provenance
from .retrieval import HybridRetriever, OpenAIEmbedder


def run_baseline_benchmark(
    cases: list[dict[str, Any]],
    benchmark_root: Path,
    output_dir: Path,
    *,
    embedding_model: str,
    top_k: int,
    client: OpenAI,
) -> dict[str, Any]:
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    ingestor = DocumentIngestor(cache_dir=Path(".cache/ingestion"))
    embedder = OpenAIEmbedder(client, embedding_model, cache_dir=Path(".cache/embeddings"))
    retriever = HybridRetriever(embedder)

    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        _write_json(
            manifest_path,
            {
                "started_at_utc": datetime.now(UTC).isoformat(),
                "benchmark_root": benchmark_root.as_posix(),
                "benchmark_sha256": _sha256_file(
                    benchmark_root / "benchmark" / "benchmark.json"
                ),
                "case_count": len(cases),
                "top_k": top_k,
                "generation": {
                    "model": GENERATION_MODEL,
                    "reasoning_effort": REASONING_EFFORT,
                    "reasoning_mode": REASONING_MODE,
                    "service_tier": SERVICE_TIER,
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "instructions_sha256": hashlib.sha256(
                        BASELINE_INSTRUCTIONS.encode("utf-8")
                    ).hexdigest(),
                },
                "embedding_model": embedding_model,
                "sdk_retry_count": 5,
                "sdk_timeout_seconds": 180,
            },
        )

    records: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        case_path = cases_dir / f"{case['case_id']}.json"
        if case_path.exists():
            record = json.loads(case_path.read_text(encoding="utf-8"))
            print(f"[{index}/{len(cases)}] {case['case_id']}: resumed", flush=True)
        else:
            record = _run_case(
                case,
                benchmark_root,
                ingestor,
                retriever,
                client,
                top_k=top_k,
            )
            _write_json(case_path, record)
            outcome = "error" if record["error"] else record["result"]["status"]
            print(f"[{index}/{len(cases)}] {case['case_id']}: {outcome}", flush=True)
        records.append(record)
        _write_json(output_dir / "summary.json", aggregate_results(records, expected_count=len(cases)))

    summary = aggregate_results(records, expected_count=len(cases))
    summary["completed_at_utc"] = datetime.now(UTC).isoformat()
    _write_json(output_dir / "summary.json", summary)
    return summary


def _run_case(
    case: dict[str, Any],
    benchmark_root: Path,
    ingestor: DocumentIngestor,
    retriever: HybridRetriever,
    client: OpenAI,
    *,
    top_k: int,
) -> dict[str, Any]:
    started = time.monotonic()
    base_record: dict[str, Any] = {
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "question": case["question"],
        "contract_stack": case["contract_stack"],
        "expected": {
            "expected_behavior": case["expected_behavior"],
            "expected_answer": case.get("expected_answer"),
            "amendment_chain": case["amendment_chain"],
        },
    }
    try:
        chunks = ingest_stack(benchmark_root, case["contract_stack"], ingestor)
        retrieved = retriever.retrieve(case["question"], chunks, top_k=top_k)
        run = DirectRAGBaseline(client).answer(case["question"], retrieved)
        provenance_errors = validate_evidence_provenance(run.result.evidence, retrieved)
        is_answer = run.result.status == ResolutionStatus.ANSWER
        base_record.update(
            {
                "result": run.result.model_dump(mode="json"),
                "api_metadata": run.api_metadata,
                "retrieved": [item.model_dump(mode="json") for item in retrieved],
                "provenance_errors": provenance_errors,
                "metrics": {
                    "operative_state_correct": operative_state_correct(case, run.result),
                    "amendment_chain_correct": amendment_chain_correct(case, run.result),
                    "abstention_correct": (
                        abstention_correct(case, run.result)
                        if case["expected_behavior"] != ResolutionStatus.ANSWER.value
                        else None
                    ),
                    "citation_provenance_valid": not provenance_errors if is_answer else None,
                    "semantic_evidence_accuracy": "NOT_SCORED",
                },
                "error": None,
            }
        )
    except Exception as exc:  # Preserve case-level failures instead of aborting the run.
        base_record.update(
            {
                "result": None,
                "api_metadata": None,
                "retrieved": [],
                "provenance_errors": [],
                "metrics": {
                    "operative_state_correct": False,
                    "amendment_chain_correct": False,
                    "abstention_correct": (
                        False if case["expected_behavior"] != ResolutionStatus.ANSWER.value else None
                    ),
                    "citation_provenance_valid": None,
                    "semantic_evidence_accuracy": "NOT_SCORED",
                },
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        )
    base_record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return base_record


def aggregate_results(records: list[dict[str, Any]], *, expected_count: int) -> dict[str, Any]:
    abstention_records = [
        record for record in records if record["metrics"]["abstention_correct"] is not None
    ]
    answer_records = [
        record for record in records if record["metrics"]["citation_provenance_valid"] is not None
    ]
    return {
        "expected_case_count": expected_count,
        "completed_case_count": len(records),
        "processing_error_count": sum(record["error"] is not None for record in records),
        "metrics": {
            "operative_state_accuracy": _metric(records, "operative_state_correct"),
            "amendment_chain_accuracy": _metric(records, "amendment_chain_correct"),
            "abstention_accuracy": _metric(abstention_records, "abstention_correct"),
            "citation_provenance_validity": _metric(answer_records, "citation_provenance_valid"),
            "semantic_evidence_accuracy": {
                "status": "NOT_SCORED",
                "reason": "A semantic evidence-accuracy method has not been approved.",
            },
        },
        "failed_case_ids": {
            "processing": [record["case_id"] for record in records if record["error"]],
            "operative_state": [
                record["case_id"]
                for record in records
                if not record["metrics"]["operative_state_correct"]
            ],
            "amendment_chain": [
                record["case_id"]
                for record in records
                if not record["metrics"]["amendment_chain_correct"]
            ],
            "abstention": [
                record["case_id"]
                for record in abstention_records
                if not record["metrics"]["abstention_correct"]
            ],
            "citation_provenance": [
                record["case_id"]
                for record in answer_records
                if not record["metrics"]["citation_provenance_valid"]
            ],
        },
        "usage": _aggregate_usage(records),
    }


def _metric(records: list[dict[str, Any]], key: str) -> dict[str, int | float | None]:
    denominator = len(records)
    numerator = sum(record["metrics"][key] is True for record in records)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "accuracy": round(numerator / denominator, 4) if denominator else None,
    }


def _aggregate_usage(records: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    for record in records:
        metadata = record.get("api_metadata") or {}
        usage = metadata.get("usage") or {}
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        totals["input_tokens"] += usage.get("input_tokens", 0)
        totals["cached_input_tokens"] += input_details.get("cached_tokens", 0)
        totals["cache_write_tokens"] += input_details.get("cache_write_tokens", 0)
        totals["output_tokens"] += usage.get("output_tokens", 0)
        totals["reasoning_tokens"] += output_details.get("reasoning_tokens", 0)
        totals["total_tokens"] += usage.get("total_tokens", 0)
    return totals


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
