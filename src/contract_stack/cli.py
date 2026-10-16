from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from openai import OpenAI

from .baseline import DirectRAGBaseline
from .benchmark import load_benchmark
from .comparison import compare_saved_runs, write_comparison
from .ingestion import DocumentIngestor
from .pipeline import ingest_stack
from .provenance import validate_evidence_provenance
from .retrieval import HybridRetriever, OpenAIEmbedder
from .resolver import ContractStackResolver
from .runner import run_baseline_benchmark, run_resolver_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Contract Stack Resolver utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    case_parser = subparsers.add_parser("baseline-case", help="Run one frozen benchmark case")
    case_parser.add_argument("case_id")
    case_parser.add_argument("--benchmark-root", type=Path, default=Path("benchmark_v1"))
    case_parser.add_argument("--top-k", type=int, default=8)
    resolver_parser = subparsers.add_parser(
        "resolver-case", help="Run the amendment-aware resolver on one frozen benchmark case"
    )
    resolver_parser.add_argument("case_id")
    resolver_parser.add_argument("--benchmark-root", type=Path, default=Path("benchmark_v1"))
    resolver_parser.add_argument("--top-k", type=int, default=8)
    benchmark_parser = subparsers.add_parser(
        "baseline-benchmark", help="Run or resume the full frozen baseline benchmark"
    )
    benchmark_parser.add_argument("--benchmark-root", type=Path, default=Path("benchmark_v1"))
    benchmark_parser.add_argument("--output-dir", type=Path)
    benchmark_parser.add_argument("--top-k", type=int, default=8)
    resolver_benchmark_parser = subparsers.add_parser(
        "resolver-benchmark", help="Run or resume the full frozen resolver benchmark"
    )
    resolver_benchmark_parser.add_argument(
        "--benchmark-root", type=Path, default=Path("benchmark_v1")
    )
    resolver_benchmark_parser.add_argument("--output-dir", type=Path)
    resolver_benchmark_parser.add_argument("--top-k", type=int, default=8)
    comparison_parser = subparsers.add_parser(
        "compare-results", help="Compare preserved baseline and resolver benchmark runs"
    )
    comparison_parser.add_argument("--baseline-dir", type=Path, required=True)
    comparison_parser.add_argument("--resolver-dir", type=Path, required=True)
    comparison_parser.add_argument("--output", type=Path, required=True)
    comparison_parser.add_argument("--benchmark-root", type=Path, default=Path("benchmark_v1"))
    args = parser.parse_args()
    if args.command == "baseline-case":
        _run_case(args.case_id, args.benchmark_root, args.top_k)
    elif args.command == "resolver-case":
        _run_resolver_case(args.case_id, args.benchmark_root, args.top_k)
    elif args.command == "baseline-benchmark":
        _run_benchmark(args.benchmark_root, args.output_dir, args.top_k)
    elif args.command == "resolver-benchmark":
        _run_resolver_benchmark(args.benchmark_root, args.output_dir, args.top_k)
    elif args.command == "compare-results":
        _compare_results(
            args.benchmark_root,
            args.baseline_dir,
            args.resolver_dir,
            args.output,
        )


def _run_case(case_id: str, benchmark_root: Path, top_k: int) -> None:
    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    cases = load_benchmark(benchmark_root / "benchmark" / "benchmark.json")
    case = next((item for item in cases if item["case_id"] == case_id), None)
    if case is None:
        raise SystemExit(f"Unknown case ID: {case_id}")

    client = OpenAI()
    ingestor = DocumentIngestor(cache_dir=Path(".cache/ingestion"))
    chunks = ingest_stack(benchmark_root, case["contract_stack"], ingestor)
    embedder = OpenAIEmbedder(client, embedding_model, cache_dir=Path(".cache/embeddings"))
    retrieved = HybridRetriever(embedder).retrieve(case["question"], chunks, top_k=top_k)
    run = DirectRAGBaseline(client).answer(case["question"], retrieved)
    output = {
        "case_id": case_id,
        "result": run.result.model_dump(mode="json"),
        "api_metadata": run.api_metadata,
        "provenance_errors": validate_evidence_provenance(run.result.evidence, retrieved),
        "retrieved_chunk_ids": [item.chunk.chunk_id for item in retrieved],
    }
    print(json.dumps(output, indent=2))


def _run_benchmark(benchmark_root: Path, output_dir: Path | None, top_k: int) -> None:
    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    cases = load_benchmark(benchmark_root / "benchmark" / "benchmark.json")
    if output_dir is None:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = Path("artifacts") / "stage3_baseline" / run_id
    client = OpenAI(max_retries=5, timeout=180.0)
    summary = run_baseline_benchmark(
        cases,
        benchmark_root,
        output_dir,
        embedding_model=embedding_model,
        top_k=top_k,
        client=client,
    )
    print(json.dumps({"output_dir": output_dir.as_posix(), "summary": summary}, indent=2))


def _run_resolver_case(case_id: str, benchmark_root: Path, top_k: int) -> None:
    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    cases = load_benchmark(benchmark_root / "benchmark" / "benchmark.json")
    case = next((item for item in cases if item["case_id"] == case_id), None)
    if case is None:
        raise SystemExit(f"Unknown case ID: {case_id}")

    client = OpenAI(max_retries=5, timeout=180.0)
    ingestor = DocumentIngestor(cache_dir=Path(".cache/ingestion"))
    chunks = ingest_stack(benchmark_root, case["contract_stack"], ingestor)
    embedder = OpenAIEmbedder(client, embedding_model, cache_dir=Path(".cache/embeddings"))
    retrieved = HybridRetriever(embedder).retrieve(case["question"], chunks, top_k=top_k)
    run = ContractStackResolver(client).resolve(case["question"], retrieved)
    output = {
        "case_id": case_id,
        "result": run.result.model_dump(mode="json"),
        "extracted_events": [event.model_dump(mode="json") for event in run.extracted_events],
        "ordered_events": [event.model_dump(mode="json") for event in run.ordered_events],
        "relationships": [item.model_dump(mode="json") for item in run.relationships],
        "extraction_provenance_errors": run.extraction_provenance_errors,
        "result_provenance_errors": validate_evidence_provenance(run.result.evidence, retrieved),
        "api_metadata": run.api_metadata,
        "retrieved_chunk_ids": [item.chunk.chunk_id for item in retrieved],
    }
    print(json.dumps(output, indent=2))


def _run_resolver_benchmark(
    benchmark_root: Path, output_dir: Path | None, top_k: int
) -> None:
    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    cases = load_benchmark(benchmark_root / "benchmark" / "benchmark.json")
    if output_dir is None:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = Path("artifacts") / "stage5_resolver" / run_id
    client = OpenAI(max_retries=5, timeout=180.0)
    summary = run_resolver_benchmark(
        cases,
        benchmark_root,
        output_dir,
        embedding_model=embedding_model,
        top_k=top_k,
        client=client,
    )
    print(json.dumps({"output_dir": output_dir.as_posix(), "summary": summary}, indent=2))


def _compare_results(
    benchmark_root: Path, baseline_dir: Path, resolver_dir: Path, output: Path
) -> None:
    cases = load_benchmark(benchmark_root / "benchmark" / "benchmark.json")
    comparison = compare_saved_runs(cases, baseline_dir, resolver_dir)
    write_comparison(output, comparison)
    print(json.dumps({"output": output.as_posix(), "comparison": comparison}, indent=2))


if __name__ == "__main__":
    main()
