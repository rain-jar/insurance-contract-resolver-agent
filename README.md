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

Each case is saved independently before the next case begins. Reusing the same output directory resumes completed cases. The summary reports operative-state, amendment-chain, abstention, and deterministic citation-provenance results separately.

Run one Stage 4 amendment-aware resolver case with:

```bash
.venv/bin/contract-stack resolver-case C09
```

The resolver output exposes extracted provision events, explicit ordering relationships, the deterministic event order, the reduced operative result, and provenance errors separately.

Stage 4 architecture and representative behavior are documented in `docs/stage4_resolver.md`.

Run or resume the approved Stage 5 resolver evaluation with:

```bash
.venv/bin/contract-stack resolver-benchmark --output-dir artifacts/stage5_resolver/<run-id>
```

Successful cases are reused. Saved connection, timeout, server, and rate-limit failures are archived under the run's `cases/failed_attempts/` directory before retry, so external failures are not mistaken for resolver results or silently discarded.

Compare a completed resolver run with the preserved Stage 3 baseline using:

```bash
.venv/bin/contract-stack compare-results \
  --baseline-dir artifacts/stage3_baseline/20261015_gpt-6.1-sol_medium_standard_run2 \
  --resolver-dir artifacts/stage5_resolver/<run-id> \
  --output artifacts/stage5_comparison/<run-id>/comparison.json
```

Stage 5 uses an inspectable deterministic Evidence Accuracy rubric rather than a separate LLM judge. Answer cases require provenance-valid citations, the frozen benchmark's effective source, a citation at the returned effective-source locator, and quoted support for every normalized expected-value component. Abstention cases remain scored by Abstention Accuracy.

After a deterministic reducer fix, replay saved extraction events without new API calls using:

```bash
.venv/bin/contract-stack replay-resolver \
  --source-dir artifacts/stage5_resolver/<source-run-id> \
  --output-dir artifacts/stage5_resolver/<replay-run-id>
```

Run the bounded relationship-driven third system from a preserved fixed-top-eight resolver run with:

```bash
.venv/bin/contract-stack relationship-benchmark \
  --source-dir artifacts/stage5_resolver/<source-run-id> \
  --output-dir artifacts/stage5_relationship/<run-id>
```

The final deterministic replays score the fixed-top-eight resolver at 90% Operative State, 80% Amendment Chain, 92% Evidence, 100% Abstention, and 100% provenance. The bounded relationship-driven resolver scores 96.67% Operative State, 96.67% Amendment Chain, 96% Evidence, 100% Abstention, and 100% provenance. It clears the 85% chain target and leaves A05 as the sole substantive failure. Full methodology and failure analysis are in `docs/stage5_evaluation.md`.

## Stage 6 productization

Stage 6 wraps the validated resolver in a single-reviewer contract-analysis application without changing the frozen experiment. Stage 6A adds an injectable structured-generation boundary and a framework-independent analysis service with document validation, ingestion, hashing, retrieval, bounded relationship resolution, and audit-ready metadata. Stage 6B adds local persistence and an HTTP API. Stage 6C adds the reviewer workflow and background analysis execution. See `docs/stage6_productization_plan.md`.

With `OPENAI_API_KEY` set, start the local application using:

```bash
.venv/bin/contract-stack-api
```

The local application binds to `127.0.0.1:8000` and stores data under the ignored `.local/contract-stack` directory. Open `http://127.0.0.1:8000/` for the reviewer interface or `http://127.0.0.1:8000/docs` for interactive API documentation. This default local mode is intentionally unauthenticated and must not be exposed to a network. See `docs/stage6_api.md` and `docs/stage6_ui.md` for the local boundary.

Stage 7 adds a separate invite-only deployment boundary without changing the local workflow or frozen benchmark. It provides signed sessions, isolated reviewer workspaces, quotas, temporary retention, hardened browser responses, and a single-instance Render Blueprint. See `docs/stage7_cloud_reviewer.md`.

For the containerized local release, place `OPENAI_API_KEY` in the ignored `.env` file and run:

```bash
docker compose up --build
```

Compose publishes only to `127.0.0.1:8000` and retains application data in a named volume. Stop it with `docker compose down`; add `--volumes` only when you intentionally want to delete all retained stacks. Optional automatic expiry, structured logs, retry behavior, backup guidance, and container operations are documented in `docs/stage6_operations.md`.
