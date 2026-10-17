# Stage 6 Local Release Operations

## Release boundary

This release is a validated, single-reviewer local pilot. It is intentionally unauthenticated and is not approved for public or multi-user network exposure. Stage 5 provides the current benchmark evidence; a separately versioned unseen evaluation and formal generalization thresholds are deferred until after pilot feedback.

## Container start and stop

Docker Desktop or another Docker Engine is required. Create an ignored `.env` file containing:

```text
OPENAI_API_KEY=your-key
```

Start the application:

```bash
docker compose up --build
```

Open `http://127.0.0.1:8000/`. Compose maps the container only to the host loopback interface and stores SQLite, uploaded sources, and derived caches in the `contract-stack-data` named volume.

Stop without deleting data:

```bash
docker compose down
```

Permanently delete the entire named volume only when intended:

```bash
docker compose down --volumes
```

Individual stacks should normally be deleted through the reviewer interface, which removes database records, originals, and stack-scoped derived caches together.

## Configuration

- `OPENAI_API_KEY` is required at application startup and must never be committed.
- `OPENAI_EMBEDDING_MODEL` defaults to `text-embedding-3-small`.
- `LOG_LEVEL` defaults to `INFO`.
- `CONTRACT_STACK_RETENTION_DAYS` optionally enables automatic expiry. It must be a positive integer and is disabled by default.
- `CONTRACT_STACK_DATA_DIR`, `CONTRACT_STACK_DATABASE`, `CONTRACT_STACK_HOST`, and `PORT` control native operation. The Compose defaults should not be broadened for this local release.

When retention is enabled, startup removes a stack only when its latest persisted stack or analysis activity is older than the configured number of days. Original files and derived caches are removed before the database record. A filesystem deletion failure preserves the database record and emits a failure event rather than pretending cleanup succeeded.

## Logging and health

`GET /health` verifies API and SQLite schema availability. The container also uses it for its Docker health check.

Application request and analysis events are emitted as one-line JSON with timestamps, correlation IDs, status, elapsed time, stack/analysis IDs where relevant, and exception type. They deliberately exclude request bodies, questions, source document text, evidence quotations, credentials, and absolute source paths. The response header `X-Request-ID` connects a browser/API response to its request event. Uvicorn process startup and shutdown lines remain ordinary text.

## Failure behavior

- Model and analysis failures are persisted as `FAILED` with a reviewer-safe message.
- A failed result page offers an explicit retry, creating a new analysis record while preserving the failed attempt for auditability.
- OpenAI SDK transient retries remain bounded by the configured client policy.
- Work left `PENDING` or `RUNNING` by a restart is marked `FAILED` at the next startup rather than shown indefinitely as active.
- The local worker is single-process and non-durable. Do not run multiple application replicas against this SQLite volume.

## Backup and recovery

Stop the application before backing up or restoring the named volume so the SQLite database and document files remain consistent. A useful backup must include the entire `/data` volume, not only the SQLite file, because originals and derived caches live beside it.

This release does not provide automated backups. Losing the volume loses uploaded stacks and analysis history. Model credentials are not stored in the volume.

## Verified release checks

- 52 automated tests pass without paid model calls.
- The container image builds successfully with Python 3.12, Tesseract OCR, packaged templates, and static assets.
- A live container smoke test returns HTTP 200 from `/health`, includes an `X-Request-ID`, and emits the expected structured request event.
- The image runs as the unprivileged `contractstack` user.
- Compose publishes `127.0.0.1:8000` rather than all host interfaces.
- The frozen benchmark validator still passes 30/30 and its SHA-256 remains unchanged.
- A manual end-to-end smoke test used the authentic First American Funds Trust 2026 financial-institution bond filing, which is absent from the repository and benchmark. For the question "What is the current Uncollectible Items of Deposit single loss limit?", the application returned USD 100,000 with Endorsement 19 as the effective source, the Item 4 amendment relationship, and traceable evidence. This is one successful external smoke test, not a formal unseen evaluation.
