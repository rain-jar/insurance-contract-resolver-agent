# Stage 6 Productization Plan

Status: approved on 2026-10-16. Stages 6A through 6C and the release-hardening portion of Stage 6D are complete. The separately versioned unseen evaluation is intentionally deferred until after the local pilot release.

## Purpose

Stage 5 established that explicit contract relationships plus bounded relationship-driven retrieval materially improve operative-term resolution. Stage 6 converts that validated research pipeline into a usable, auditable application without changing the frozen benchmark or rewriting the experimental history.

The recommended first product is a single-reviewer contract-analysis workspace. A reviewer uploads one contract stack, asks a question about a supported attribute, and receives either:

- the current operative value, effective source, amendment chain, and source-grounded evidence; or
- an explicit unsupported or insufficient-evidence outcome with the reason.

This is a decision-support tool, not an autonomous legal decision-maker.

## Proposed first-release boundary

### Included

- PDF, HTML, and TXT contract-stack upload.
- Questions about `LIMIT`, `DEDUCTIBLE`, and `POLICY_PERIOD`.
- The Stage 5 relationship-driven resolver as the resolution engine.
- Bounded OCR and bounded relationship-driven retrieval.
- Inspectable answer, chain, evidence quotations, and source locators.
- Explicit abstention and unsupported-attribute states.
- Persistent analysis records and an audit trail sufficient to reproduce what the system saw and returned.
- Local development and containerized deployment.
- Automated unit, integration, and end-to-end tests.

### Deferred

- Autonomous coverage or claims decisions.
- Fine-tuning or benchmark-specific prompting.
- Additional insurance attributes before separate evaluation.
- Multi-tenant billing, enterprise identity, and complex role administration.
- A graph database or vector database until measured scale requires one.
- Silent fallback to unbounded search when evidence is missing.
- Changes to the frozen Stage 1–5 benchmark or preserved results.

## Proposed architecture

The production path should wrap, not replace, the validated resolver.

1. **Domain core** — existing typed models, provenance checks, relationship construction, deterministic reduction, and bounded expansion remain framework-independent.
2. **Application service** — coordinates stack creation, ingestion, analysis, persistence, and status transitions behind a stable interface.
3. **Persistence** — SQLite for the first release, storing stack metadata, document hashes, questions, results, model configuration, usage, and errors. Source files live in a controlled application-data directory rather than in the database.
4. **HTTP API** — FastAPI endpoints for stack upload, analysis submission, status, result retrieval, and health checks. API schemas reuse or explicitly map to the existing Pydantic contracts.
5. **Review interface** — a small server-rendered web UI showing the answer and amendment chain beside evidence. Avoid a separate JavaScript application until user needs justify it.
6. **Model boundary** — one adapter owns OpenAI calls, timeouts, retry policy, model configuration, and usage metadata. The resolver remains testable with a fake adapter.
7. **Observability and safety** — structured logs, per-analysis correlation IDs, no document text in ordinary logs, file/type/size limits, safe filenames, explicit data-retention behavior, and visible failure states.

## Delivery phases

### Stage 6A — Requirements and production seams

- Approve the first user and workflow.
- Define latency, cost, file-size, privacy, and retention expectations.
- Refactor model calls behind an injectable interface.
- Introduce an application-level analysis service without changing resolver behavior.
- Add regression tests proving Stage 5 behavior is preserved.

Completed with an injectable structured-generation adapter and a framework-independent `ContractAnalysisService`. The service validates production inputs, ingests and hashes local documents, performs top-eight retrieval, invokes the bounded relationship resolver, and returns audit-ready retrieval, expansion, timing, and generation-call metadata. Raw source paths and document text are not included in the audit record.

### Stage 6B — Persistent API

- Add SQLite migrations and repositories.
- Add secure stack ingestion and analysis endpoints.
- Persist configuration, inputs, outputs, errors, provenance, and usage.
- Add API integration tests using fake model responses; no API spending in ordinary tests.

Completed with a versioned SQLite schema, repository, controlled local document store, stack-scoped derived caches, loopback-only FastAPI launcher, stack lifecycle endpoints, synchronous analysis lifecycle endpoints, health check, and fake-model API integration tests. See `docs/stage6_api.md`.

Stage 6B verification brings the suite to 46 passing tests. The API schema exposes health, stack create/list/read/delete, analysis create/list/read, and no paid model calls are used in the integration suite. The frozen benchmark validator and hash remain unchanged.

### Stage 6C — Reviewer interface

- Upload and organize a contract stack.
- Submit supported questions.
- Display operative value, effective source, amendment timeline, citations, and abstention reasons.
- Provide clear progress and retry behavior for long-running model calls.

Completed with a local, server-rendered reviewer workspace for stack upload, stack detail and deletion, question submission, analysis history, background status polling, and auditable result review. Answer views place the operative value, effective source, ordered amendment chain, and evidence quotations together; non-answer and failed states remain explicit. A single in-process worker keeps model work off the request thread, and interrupted work is marked failed on restart rather than left indefinitely pending. Browser forms use randomized double-submit CSRF tokens, and unsafe requests are restricted to local origins. See `docs/stage6_ui.md`.

Stage 6C verification brings the suite to 50 passing tests. The full upload-to-result-to-delete path is exercised with fake generation, so no paid API calls are made. Desktop browser QA confirms the dashboard and completed relationship-resolution view render correctly; responsive behavior is covered by the interface's explicit tablet and mobile breakpoints.

### Stage 6D — Hardening and unseen evaluation

- Containerize and document deployment.
- Add limits, retention controls, observability, and failure recovery.
- Assemble a new, separately versioned unseen evaluation set reviewed by domain experts.
- Establish release thresholds for accuracy, abstention, latency, and cost.

The user approved splitting this phase. Release hardening is complete: the application has a non-root container image with OCR support and a health check, loopback-only Compose packaging with persistent storage, privacy-safe structured request and analysis events, per-request correlation IDs, explicit reviewer retry for failed work, startup recovery for interrupted jobs, and opt-in automatic retention cleanup based on latest stack activity. See `docs/stage6_operations.md`.

The unseen evaluation set and formal generalization thresholds are deferred until after the local pilot release. Stage 5 remains the current experimental evidence; the release must be described as a validated local pilot/demo rather than as broadly production-validated. The future evaluation will be separately versioned so it does not rewrite the frozen Stage 1–5 benchmark or its historical results.

## Acceptance criteria for the first release

- A reviewer can complete the upload-to-auditable-result workflow without using the CLI.
- Every answer exposes its effective source, ordered chain, and traceable evidence.
- Every analysis records the exact model and resolver configuration used.
- Missing or contradictory evidence produces an explicit non-answer rather than an unsupported guess.
- Automated tests do not require paid model calls.
- Existing Stage 1–5 tests and the frozen benchmark validator continue to pass.
- Uploaded documents and model credentials are never committed to source control or emitted in ordinary logs.

## Approved operational defaults

- The first release is a trusted, single-reviewer local application.
- Uploaded source documents are retained locally for reproducibility until the reviewer deletes the stack.
- The first delivery stack is FastAPI plus a server-rendered interface and SQLite.
- A stack may contain at most 50 documents, 25 MiB per document, and 100 MiB total in the initial release. These are safety limits, not claims about demonstrated processing scale.
- Questions are limited to 2,000 characters.
- Resolution keeps the validated top-eight initial retrieval, at most one relationship-expansion round, at most two added chunks, and at most one additional extraction call.
- Model timeout and retry behavior remains explicit, and every successful analysis records model configuration and token usage. Ordinary automated tests use injected fake generation and do not spend API credits.
- Source text is excluded from ordinary application logs. The initial retention policy is manual deletion; configurable automatic expiry is deferred until the persistence phase.
- Manual deletion in the persistence phase must cover original files and derived ingestion or embedding caches.
- Until production latency has been measured, elapsed time and token usage are recorded rather than presenting an unsupported latency guarantee. Each analysis is bounded to one initial extraction call and at most one expansion extraction call.

## Approved implementation decisions

1. The first release is a single-reviewer internal/local application rather than a public or multi-tenant service.
2. Source documents may be stored locally for reproducibility, with manual deletion.
3. FastAPI plus a server-rendered interface is the initial delivery stack.

These defaults produce the smallest credible product while preserving an upgrade path to stronger identity, storage, job infrastructure, and a richer frontend.

## Stage 6A verification

- 38 automated tests pass, including application-service success, unsupported-question, unsafe-name, and file-size cases.
- Existing baseline and resolver tests pass through the OpenAI compatibility adapter.
- The frozen benchmark validator passes all 30 cases.
- The frozen benchmark SHA-256 remains `482dbb524447b54fada943bfab05f7d0be68c0566614df8e121a326ca1f2c7e4`.
- No paid API calls were used for Stage 6A verification.
