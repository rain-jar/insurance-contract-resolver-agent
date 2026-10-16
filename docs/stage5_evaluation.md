# Stage 5 Comparative Evaluation

## Approved experiment

The preserved Stage 3 baseline and the Stage 4 resolver are compared on the same frozen 30-case benchmark. Both systems use the same parsed chunks, hybrid retrieval, top-eight evidence, embedding model, `gpt-6.1-sol` generation model, medium reasoning effort, standard reasoning mode, and Standard service tier. The comparison command rejects mismatched manifests before calculating deltas.

The baseline is not rerun. Its preserved second run avoids additional cost and stochastic variation while retaining its case-level outputs and configuration manifest.

## Metrics

- Operative State Accuracy uses exact status and normalized-value matching.
- Amendment-Chain Accuracy uses exact ordered source, operation, and normalized step-value matching.
- Abstention Accuracy covers the five frozen non-answer cases.
- Citation Provenance Validity verifies that returned quotations occur in supplied retrieved chunks.
- Evidence Accuracy covers the 25 frozen answer cases. It requires provenance-valid citations, agreement with the frozen expected effective source, a citation at the returned effective-source locator, and quoted support for every expected amount/currency or policy-period endpoint.

The deterministic Evidence Accuracy rubric is intentionally narrower and more inspectable than an LLM judge. Amendment meaning and ordering are evaluated by Amendment-Chain Accuracy rather than being scored a second time through an opaque semantic judge. Manual review is used to analyze failures and representative passes, not to silently change the automated score.

## Preservation and resume behavior

Each resolver case is written before the next case begins. Successful and non-retryable case results are reused on resume. External connection, timeout, server, or rate-limit errors are archived under `cases/failed_attempts/` before retrying; this prevents infrastructure failures from becoming permanent resolver failures while retaining the original attempt record.

## Current run state

Run `artifacts/stage5_resolver/20261016_gpt-6.1-sol_medium_standard_run1` stopped when the API reported `credit_balance_exhausted` after A09:

- A01–A09 have valid resolver results.
- A10–C07 currently contain external quota-error records.
- C08–ADV05 were not attempted.
- The partial summary is invalid for baseline-versus-resolver conclusions.

Among the nine valid completed cases, A01–A04 and A06–A09 pass Operative State, Evidence, and Amendment-Chain Accuracy. A05 repeats the known shared-retrieval failure because the relevant Endorsement 2 provision is absent from the common top-eight evidence. These observations are preliminary until all 30 cases complete.
