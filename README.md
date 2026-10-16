# Contract Stack Resolver

An independent MVP testing whether explicitly modeling relationships between base insurance policies and endorsements/amendments resolves currently operative terms more reliably than conventional retrieval-based document Q&A.

The frozen benchmark is under `benchmark_v1/`. Stage 3 implements a credible retrieval/RAG baseline using shared ingestion and retrieval components that will later also be used by the amendment-aware resolver.

## Development setup

Python 3.12 and the `tesseract` executable are required. Tesseract is used only when a PDF page has no usable embedded text.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

API-backed commands read `OPENAI_API_KEY` and optionally `OPENAI_EMBEDDING_MODEL`. Stage 3 generation is locked to `gpt-6.1-sol` with medium reasoning, standard mode, and the Standard service tier. Each generation result records the returned model identifier, actual service tier, timestamp, and token usage. Secrets must not be committed.

Run or resume the full frozen baseline benchmark with:

```bash
.venv/bin/contract-stack baseline-benchmark --output-dir artifacts/stage3_baseline/<run-id>
```

Each case is saved independently before the next case begins. Reusing the same output directory resumes completed cases. The summary reports operative-state, amendment-chain, abstention, and deterministic citation-provenance results separately. Semantic Evidence Accuracy remains explicitly unscored until its evaluation method is approved.

Run one Stage 4 amendment-aware resolver case with:

```bash
.venv/bin/contract-stack resolver-case C09
```

The resolver output exposes extracted provision events, explicit ordering relationships, the deterministic event order, the reduced operative result, and provenance errors separately.

Stage 4 architecture and representative behavior are documented in `docs/stage4_resolver.md`. The full resolver benchmark is intentionally deferred to the Stage 5 comparative-evaluation gate.
