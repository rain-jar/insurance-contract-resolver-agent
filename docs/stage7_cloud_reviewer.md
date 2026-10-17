# Stage 7: authenticated cloud reviewer

## Boundary

Stage 7 packages the existing upload-to-auditable-result workflow as a private,
invite-only cloud reviewer. It does not make the application a public anonymous
upload service and does not change the resolver or the frozen benchmark.

Each access code maps to one stable reviewer identifier. Stack and analysis
queries are scoped to that identifier, so reviewers cannot enumerate or open
one another's records. There is no public registration flow.

## Render deployment

`render.yaml` defines one free Docker web service in the Ohio region. SQLite,
uploaded files, and derived caches use the service's ephemeral filesystem. The
service remains at one instance because the in-process analysis worker and
filesystem workspace are intentionally single-instance.

Render prompts for these secrets during initial Blueprint creation:

- `OPENAI_API_KEY`: the project-scoped OpenAI API key used by the resolver.
- `CONTRACT_STACK_INVITE_CODES`: a JSON object mapping reviewer IDs to unique,
  randomly generated codes of at least 20 characters. Example shape only:
  `{"reviewer-name":"replace-with-a-random-secret"}`.

Render generates `CONTRACT_STACK_SESSION_SECRET`. Never commit any of these
values. Hosted sessions last eight hours, use signed HTTPS-only cookies, and are
invalidated when their reviewer ID is removed from the invite configuration.

The Blueprint also enables a seven-day upper-bound application retention policy
and conservative per-reviewer/global quotas. In practice, Render may erase the
entire workspace sooner whenever the free service spins down, restarts, or is
redeployed. Manual stack deletion removes the database record, original uploads,
and derived caches immediately from the current instance.

## Operational limits

- This is a bounded portfolio/pilot service, not a production multi-tenant SaaS.
- Free services spin down after inactivity. Waking the service can take about a
  minute, and all prior stacks and results can disappear at spin-down, restart,
  or deployment. Reviewers must download or record anything they need before
  leaving the session.
- An in-progress analysis can be lost if the service stops. There is no durable
  retry queue because the free filesystem is intentionally disposable.
- The free 512 MB compute size may be insufficient for large PDF/OCR work. Keep
  uploads small; a paid vertical upgrade is required if representative files
  exhaust memory.
- Quotas limit accidental model spend but are not a billing cap. Configure OpenAI
  project budgets and alerts independently.

## Verification gate

Before sharing the URL:

1. Confirm `/health` reports database schema version 2.
2. Confirm unauthenticated HTML redirects to `/login` and unauthenticated API
   requests receive HTTP 401.
3. Sign in with a dedicated smoke-test invite.
4. Upload a non-benchmark contract stack, run one analysis, and inspect the
   operative result, amendment chain, evidence, and technical audit details.
5. Delete the stack and confirm its URL returns HTTP 404.
6. Use a second invite to confirm the first reviewer's stack is not visible.
7. Remove the smoke-test invite after verification.

Do not publish the URL as ready until this gate passes.
