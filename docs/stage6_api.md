# Stage 6B Persistent API

## Status

Stage 6B is complete. It exposes the Stage 6A application service through a local FastAPI API and persists contract stacks and analysis records in SQLite.

## Local runtime

Set `OPENAI_API_KEY` and start:

```bash
.venv/bin/contract-stack-api
```

The server binds only to `127.0.0.1:8000`. Interactive API documentation is available at `http://127.0.0.1:8000/docs`. The data directory defaults to `.local/contract-stack` and is excluded from Git.

Optional configuration:

- `CONTRACT_STACK_DATA_DIR` changes the local application-data directory.
- `CONTRACT_STACK_DATABASE` changes the SQLite database location.
- `OPENAI_EMBEDDING_MODEL` changes the embedding model; the approved default remains `text-embedding-3-small`.
- `CONTRACT_STACK_RETENTION_DAYS` enables opt-in startup expiry based on latest stack activity; expiry is disabled by default.
- `LOG_LEVEL` changes the structured application-event threshold.

## Endpoints

- `GET /health` checks the API and database schema.
- `POST /api/stacks` accepts a title and one or more PDF, HTML, or TXT files.
- `GET /api/stacks` lists saved stacks without returning document content.
- `GET /api/stacks/{stack_id}` returns stack and document metadata.
- `DELETE /api/stacks/{stack_id}` deletes the database records, original files, ingestion cache, and embedding cache.
- `POST /api/stacks/{stack_id}/analyses` accepts a supported question and runs the bounded relationship resolver.
- `GET /api/stacks/{stack_id}/analyses` lists compact analysis-history records.
- `GET /api/analyses/{analysis_id}` returns status and the stored result or failure information.

The JSON API retains the synchronous Stage 6B analysis endpoint for programmatic callers. The Stage 6C reviewer form submits analyses to a bounded, single-worker background executor and polls a compact status endpoint, while both paths use the same processor and persist the same `PENDING`, `RUNNING`, `COMPLETED`, and `FAILED` transitions.

## Persistence and audit record

SQLite migration version 1 stores:

- stack identity, title, and creation time;
- document display name, controlled relative path, byte size, and SHA-256;
- analysis question, lifecycle timestamps, status, result, and failure details.

A completed analysis additionally records:

- the operative result and amendment chain;
- extracted and ordered provision events and relationships;
- initial and expansion model metadata and token usage;
- embedding model, cache behavior, and token usage;
- retrieval and relationship-expansion bounds;
- provenance-validation errors;
- document hashes and execution timing.

Retrieved source text is not duplicated into the audit record. Original documents remain available in the controlled stack directory, while citations retain the exact evidence quotations needed for review.

## Local security boundary

- The server binds to loopback and accepts only trusted local host headers.
- There is no authentication because the approved first release is a trusted single-reviewer local application. It must not be exposed to a network.
- Stack IDs are UUIDs and all resolved document paths must remain beneath their stack directory.
- Uploads are streamed through document and aggregate size limits into an isolated incoming directory, then atomically moved into place.
- Unsafe filenames, duplicate names, unsupported extensions, empty files, and oversized uploads are rejected.
- The application-data directory is mode `0700`; the SQLite database is mode `0600`.
- Deleting a stack removes originals and stack-scoped derived caches before deleting its database record.
- API responses do not expose absolute filesystem paths.
- Model credentials are read by the OpenAI SDK and are never stored in SQLite.

Stage 6C browser forms use randomized double-submit CSRF tokens, and unsafe browser/API mutations reject non-local origins. Background work uses one in-process worker, with interrupted `PENDING` or `RUNNING` records marked failed when the application restarts. Authentication, durable external jobs, richer retention controls, and deployable network security remain future work and must be implemented before changing the local-only boundary.

The Stage 6D local release adds an explicit retry action for failed reviewer analyses, per-request `X-Request-ID` correlation, privacy-safe structured request and analysis events, and optional age-based retention cleanup. These additions do not change the local-only security boundary; see `docs/stage6_operations.md`.

## Verification

API integration tests use injected fake generation and lexical retrieval, so ordinary tests make no paid API calls. Tests cover successful upload-analysis-read-delete behavior, restart persistence, safe filename enforcement, failed-analysis persistence, atomic upload cleanup, derived-cache deletion, model usage audit metadata, and schema health.
