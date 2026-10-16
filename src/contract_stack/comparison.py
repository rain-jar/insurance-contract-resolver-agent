from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evaluation import evidence_accuracy_errors
from .models import ResolutionResult, ResolutionStatus
from .runner import aggregate_results


COMPARABILITY_FIELDS = (
    "benchmark_sha256",
    "case_count",
    "top_k",
    "embedding_model",
)
GENERATION_COMPARABILITY_FIELDS = (
    "model",
    "reasoning_effort",
    "reasoning_mode",
    "service_tier",
    "max_output_tokens",
)
COMPARISON_METRICS = (
    "operative_state_accuracy",
    "evidence_accuracy",
    "amendment_chain_accuracy",
    "abstention_accuracy",
    "citation_provenance_validity",
)


def compare_saved_runs(
    cases: list[dict[str, Any]], baseline_dir: Path, resolver_dir: Path
) -> dict[str, Any]:
    baseline_manifest = _read_json(baseline_dir / "manifest.json")
    resolver_manifest = _read_json(resolver_dir / "manifest.json")
    _validate_comparability(baseline_manifest, resolver_manifest)

    case_map = {case["case_id"]: case for case in cases}
    baseline_records = _load_and_rescore(baseline_dir / "cases", case_map)
    resolver_records = _load_and_rescore(resolver_dir / "cases", case_map)
    expected_ids = list(case_map)
    if [record["case_id"] for record in baseline_records] != expected_ids:
        raise ValueError("The baseline run does not contain exactly the frozen benchmark cases.")
    if [record["case_id"] for record in resolver_records] != expected_ids:
        raise ValueError("The resolver run does not contain exactly the frozen benchmark cases.")

    baseline_summary = aggregate_results(baseline_records, expected_count=len(cases))
    resolver_summary = aggregate_results(resolver_records, expected_count=len(cases))
    deltas = {
        metric: _accuracy(resolver_summary, metric) - _accuracy(baseline_summary, metric)
        for metric in COMPARISON_METRICS
    }
    return {
        "comparability": {
            "status": "PASS",
            "shared_benchmark_sha256": baseline_manifest["benchmark_sha256"],
            "shared_top_k": baseline_manifest["top_k"],
            "shared_embedding_model": baseline_manifest["embedding_model"],
            "shared_generation_configuration": {
                key: baseline_manifest["generation"][key]
                for key in GENERATION_COMPARABILITY_FIELDS
            },
            "baseline_instructions_sha256": baseline_manifest["generation"][
                "instructions_sha256"
            ],
            "resolver_instructions_sha256": resolver_manifest["generation"][
                "instructions_sha256"
            ],
        },
        "baseline": baseline_summary,
        "resolver": resolver_summary,
        "resolver_minus_baseline_accuracy": deltas,
        "cases": [
            {
                "case_id": case_id,
                "baseline_metrics": baseline_records[index]["metrics"],
                "resolver_metrics": resolver_records[index]["metrics"],
                "baseline_evidence_errors": baseline_records[index].get(
                    "evidence_accuracy_errors"
                ),
                "resolver_evidence_errors": resolver_records[index].get(
                    "evidence_accuracy_errors"
                ),
            }
            for index, case_id in enumerate(expected_ids)
        ],
    }


def _load_and_rescore(
    cases_dir: Path, case_map: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case_id, case in case_map.items():
        path = cases_dir / f"{case_id}.json"
        if not path.exists():
            raise ValueError(f"Missing saved case result: {path}")
        record = _read_json(path)
        if record["case_id"] != case_id:
            raise ValueError(f"Saved case ID mismatch in {path}")
        records.append(_rescore_evidence(case, record))
    return records


def _rescore_evidence(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    rescored = dict(record)
    metrics = dict(record["metrics"])
    result_data = record.get("result")
    if result_data is None:
        errors = (
            ["The case failed before evidence could be evaluated."]
            if case["expected_behavior"] == ResolutionStatus.ANSWER.value
            else None
        )
    else:
        result = ResolutionResult.model_validate(result_data)
        provenance_errors = record.get(
            "result_provenance_errors", record.get("provenance_errors", [])
        )
        errors = evidence_accuracy_errors(case, result, provenance_errors)
    metrics["evidence_accurate"] = None if errors is None else not errors
    metrics["semantic_evidence_accuracy"] = "NOT_SCORED"
    rescored["metrics"] = metrics
    rescored["evidence_accuracy_errors"] = errors
    return rescored


def _validate_comparability(
    baseline_manifest: dict[str, Any], resolver_manifest: dict[str, Any]
) -> None:
    mismatches = [
        field
        for field in COMPARABILITY_FIELDS
        if baseline_manifest.get(field) != resolver_manifest.get(field)
    ]
    mismatches.extend(
        f"generation.{field}"
        for field in GENERATION_COMPARABILITY_FIELDS
        if baseline_manifest.get("generation", {}).get(field)
        != resolver_manifest.get("generation", {}).get(field)
    )
    if mismatches:
        raise ValueError(
            "Baseline and resolver runs are not directly comparable; mismatched fields: "
            + ", ".join(mismatches)
        )


def _accuracy(summary: dict[str, Any], metric: str) -> float:
    accuracy = summary["metrics"][metric]["accuracy"]
    if accuracy is None:
        raise ValueError(f"Metric {metric} has no denominator.")
    return accuracy


def write_comparison(path: Path, comparison: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
