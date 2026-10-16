import json
from pathlib import Path

from contract_stack.comparison import compare_saved_runs
from contract_stack.models import (
    Attribute,
    EvidenceRef,
    ExtractionMethod,
    NormalizedValue,
    OperativeState,
    ResolutionResult,
    ResolutionStatus,
    SourceRef,
)


def test_compare_saved_runs_rescores_evidence_and_checks_shared_configuration(
    tmp_path: Path,
) -> None:
    baseline_dir = tmp_path / "baseline"
    resolver_dir = tmp_path / "resolver"
    cases = [_answer_case(), _abstention_case()]
    for run_dir in (baseline_dir, resolver_dir):
        (run_dir / "cases").mkdir(parents=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(_manifest("baseline" if run_dir == baseline_dir else "resolver")),
            encoding="utf-8",
        )
        _write_record(run_dir, cases[0], _answer_result())
        _write_record(run_dir, cases[1], _abstention_result())

    comparison = compare_saved_runs(cases, baseline_dir, resolver_dir)

    assert comparison["comparability"]["status"] == "PASS"
    assert comparison["baseline"]["metrics"]["evidence_accuracy"]["accuracy"] == 1.0
    assert comparison["resolver_minus_baseline_accuracy"]["operative_state_accuracy"] == 0.0


def _manifest(instructions: str) -> dict:
    return {
        "benchmark_sha256": "frozen",
        "case_count": 2,
        "top_k": 8,
        "embedding_model": "embedding-model",
        "generation": {
            "model": "generation-model",
            "reasoning_effort": "medium",
            "reasoning_mode": "standard",
            "service_tier": "default",
            "max_output_tokens": 25_000,
            "instructions_sha256": instructions,
        },
    }


def _answer_case() -> dict:
    return {
        "case_id": "C01",
        "case_type": "controlled",
        "expected_behavior": "ANSWER",
        "expected_answer": {"amount": 5_000_000, "currency": "USD"},
        "effective_source": "endorsement.txt",
        "amendment_chain": [],
    }


def _abstention_case() -> dict:
    return {
        "case_id": "ADV01",
        "case_type": "adversarial",
        "expected_behavior": "INSUFFICIENT_EVIDENCE",
        "expected_answer": None,
        "effective_source": None,
        "amendment_chain": [],
    }


def _answer_result() -> ResolutionResult:
    return ResolutionResult(
        status=ResolutionStatus.ANSWER,
        attribute=Attribute.LIMIT,
        subject="On Premises",
        operative_state=OperativeState.ACTIVE,
        normalized_value=NormalizedValue(
            amount=5_000_000, currency="USD", start=None, end=None
        ),
        effective_source=SourceRef(
            document_path="endorsement.txt",
            provision_label="Endorsement 8",
            locator="paragraph:1",
        ),
        evidence=[
            EvidenceRef(
                document_path="endorsement.txt",
                locator="paragraph:1",
                quote="The limit is USD 5,000,000.",
                extraction_method=ExtractionMethod.TEXT,
            )
        ],
        amendment_chain=[],
        reason="Supported.",
    )


def _abstention_result() -> ResolutionResult:
    return ResolutionResult(
        status=ResolutionStatus.INSUFFICIENT_EVIDENCE,
        attribute=Attribute.LIMIT,
        subject="On Premises",
        operative_state=OperativeState.UNKNOWN,
        normalized_value=None,
        effective_source=None,
        evidence=[],
        amendment_chain=[],
        reason="Conflicting amendments.",
    )


def _write_record(run_dir: Path, case: dict, result: ResolutionResult) -> None:
    is_answer = result.status == ResolutionStatus.ANSWER
    record = {
        "case_id": case["case_id"],
        "result": result.model_dump(mode="json"),
        "provenance_errors": [],
        "metrics": {
            "operative_state_correct": True,
            "amendment_chain_correct": True,
            "abstention_correct": None if is_answer else True,
            "citation_provenance_valid": True if is_answer else None,
            "semantic_evidence_accuracy": "NOT_SCORED",
        },
        "error": None,
        "api_metadata": None,
    }
    (run_dir / "cases" / f"{case['case_id']}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
