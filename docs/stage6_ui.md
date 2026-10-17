# Stage 6C Reviewer Interface

## Status

Stage 6C is complete. It provides a local reviewer workflow over the Stage 6B API and persistence layer without changing the validated resolver or frozen benchmark.

## Reviewer workflow

Start the application with `OPENAI_API_KEY` set:

```bash
.venv/bin/contract-stack-api
```

Open `http://127.0.0.1:8000/` and:

1. create a contract stack by uploading its base policy, endorsements, riders, or amendments;
2. ask a question about a supported `LIMIT`, `DEDUCTIBLE`, or `POLICY_PERIOD` term;
3. leave the processing page open while it polls the persisted analysis state; and
4. review the operative value, effective source, ordered amendment chain, evidence quotations, explanation, and technical audit details.

Saved stacks retain their source documents and analysis history until the reviewer deletes the stack. Deletion removes database records, originals, and stack-scoped derived caches.

## Execution model

Reviewer submissions use a single in-process background worker. The browser receives an analysis ID immediately and polls `GET /analyses/{analysis_id}/status` until the record completes or fails. The existing JSON API submission remains synchronous for compatibility and deterministic integration use; both entry points share the same analysis processor and persistence transitions.

This worker is intentionally bounded to the approved single-reviewer local product. It is not durable across process restarts. On startup, any analysis left `PENDING` or `RUNNING` is marked `FAILED` with an interruption error so the interface never presents abandoned work as active. Durable queues and automatic retries belong to Stage 6D or a later deployment stage.

## Safety boundary

- HTML templates autoescape reviewer and model-provided text.
- Every mutating browser form requires a randomized double-submit CSRF token held in an HTTP-only, same-site cookie and rendered into the form.
- Unsafe HTTP mutations reject non-local `Origin` and `Referer` values.
- Trusted-host validation and the loopback-only launcher preserve the local boundary.
- Upload type, filename, document count, individual size, total size, and question length limits remain enforced by the shared application and storage layers.
- Model failures are persisted and shown as failures; they are not converted into unsupported answers.
- No authentication is provided. The application must not be exposed to a network.

## Verification

- 50 automated tests pass.
- UI integration tests cover upload, background execution, status polling, completed result rendering, deletion, CSRF rejection, and cross-site mutation rejection.
- Tests inject fake generation and make no paid model calls.
- Browser QA confirms the dashboard and completed result view, including the operative endorsement, two-step amendment chain, and traceable evidence.
- The interface includes explicit tablet and mobile layout breakpoints plus reduced-motion handling.
- The frozen benchmark validator and SHA-256 verification continue to pass without benchmark modification.

## Deferred to Stage 6D

- durable external jobs and automatic retry policy for a multi-user deployment;
- authentication and network deployment controls;
- a new, separately versioned unseen evaluation set and release thresholds for quality, abstention, latency, and cost.

Container packaging, local operating documentation, structured application events, request IDs, opt-in retention expiry, reviewer-triggered retry, and explicit restart recovery were subsequently completed in the release-hardening portion of Stage 6D. See `docs/stage6_operations.md`.
