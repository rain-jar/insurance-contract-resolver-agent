from contract_stack.runner import (
    _combine_api_metadata,
    _is_retryable_saved_error,
    aggregate_results,
)


def _record(
    case_id: str,
    *,
    operative: bool,
    chain: bool,
    abstention: bool | None,
    provenance: bool | None,
    error: bool = False,
) -> dict:
    return {
        "case_id": case_id,
        "metrics": {
            "operative_state_correct": operative,
            "amendment_chain_correct": chain,
            "abstention_correct": abstention,
            "citation_provenance_valid": provenance,
        },
        "error": {"type": "TestError", "message": "failed"} if error else None,
        "api_metadata": {
            "usage": {
                "input_tokens": 10,
                "input_tokens_details": {"cached_tokens": 4, "cache_write_tokens": 6},
                "output_tokens": 3,
                "output_tokens_details": {"reasoning_tokens": 1},
                "total_tokens": 13,
            }
        },
    }


def test_aggregate_results_keeps_metrics_separate_and_counts_errors_as_failures() -> None:
    records = [
        _record("A01", operative=True, chain=True, abstention=None, provenance=True),
        _record(
            "ADV01",
            operative=False,
            chain=False,
            abstention=False,
            provenance=None,
            error=True,
        ),
    ]

    summary = aggregate_results(records, expected_count=2)

    assert summary["metrics"]["operative_state_accuracy"] == {
        "numerator": 1,
        "denominator": 2,
        "accuracy": 0.5,
    }
    assert summary["metrics"]["abstention_accuracy"] == {
        "numerator": 0,
        "denominator": 1,
        "accuracy": 0.0,
    }
    assert summary["metrics"]["citation_provenance_validity"] == {
        "numerator": 1,
        "denominator": 1,
        "accuracy": 1.0,
    }
    assert summary["metrics"]["semantic_evidence_accuracy"]["status"] == "NOT_SCORED"
    assert summary["failed_case_ids"]["processing"] == ["ADV01"]
    assert summary["usage"]["total_tokens"] == 26


def test_only_external_api_failures_are_retryable_on_resume() -> None:
    assert _is_retryable_saved_error(
        {"error": {"type": "RateLimitError", "message": "credit exhausted"}}
    )
    assert not _is_retryable_saved_error(
        {"error": {"type": "ValidationError", "message": "invalid model output"}}
    )
    assert not _is_retryable_saved_error({"error": None})


def test_combined_api_metadata_sums_paired_call_usage() -> None:
    initial = {
        "usage": {
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 2, "cache_write_tokens": 8},
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 1},
            "total_tokens": 14,
        }
    }
    expansion = {
        "usage": {
            "input_tokens": 5,
            "input_tokens_details": {"cached_tokens": 1, "cache_write_tokens": 4},
            "output_tokens": 3,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 8,
        }
    }

    combined = _combine_api_metadata(initial, expansion)

    assert combined is not None
    assert combined["usage"] == {
        "input_tokens": 15,
        "output_tokens": 7,
        "total_tokens": 22,
        "input_tokens_details": {"cached_tokens": 3, "cache_write_tokens": 12},
        "output_tokens_details": {"reasoning_tokens": 3},
    }
