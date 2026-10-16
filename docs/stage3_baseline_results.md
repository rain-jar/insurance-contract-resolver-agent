# Stage 3 Baseline Results

## Final baseline run

The final Stage 3 baseline is run 2:

`artifacts/stage3_baseline/20261015_gpt-6.1-sol_medium_standard_run2`

It ran all 30 frozen cases with hybrid BM25+/embedding retrieval (`top_k=8`) followed by one direct structured `gpt-6.1-sol` response at medium reasoning effort on the Standard service tier. The manifest records the generation configuration plus SHA-256 hashes of the frozen benchmark and baseline instructions. Every case record preserves its expected result, retrieved chunks, model result or processing error, provenance result, metric results, token usage, and elapsed time.

Run 1 is preserved separately. It revealed that the initial prompt contradicted frozen benchmark assumptions A1 and A5 by failing to tell the model that endorsement numbers may establish order and that labeled synthetic controlled amendments are valid benchmark material. The prompt was corrected narrowly and a clean run 2 was performed. No benchmark data, retrieval behavior, result schema, or relationship-resolution machinery changed between the runs.

## Metrics

| Metric | Result | Notes |
|---|---:|---|
| Operative State Accuracy | 27/30 (90.00%) | Exact normalized value/status comparison; processing errors count as failures. |
| Amendment-Chain Accuracy | 19/30 (63.33%) | Exact ordered source, operation, and normalized step-value comparison. |
| Abstention Accuracy | 3/5 (60.00%) | Only the five explicit non-answer cases are in the denominator. |
| Citation Provenance Validity | 25/25 (100.00%) | All citations in valid `ANSWER` results resolve to retrieved text. This is not semantic Evidence Accuracy. |
| Semantic Evidence Accuracy | Not scored | No semantic evidence-evaluation method has been approved. |

There were two result-schema processing failures. Total generation usage recorded by successful API responses was 166,672 input tokens, 17,219 output tokens, and 443 reasoning tokens (183,891 total). Embedding usage is cached separately and is not included in these totals.

## Failure analysis

### Operative-state failures

- **A05 — retrieval miss.** The model returned the $1,250,000 declarations value for Computer System Fraud. The relevant Endorsement 2 provision establishing $1,775,000 was not present in the top-eight retrieved chunks. This is a retrieval failure, not an amendment-ordering failure.
- **ADV01 and ADV03 — invalid structured abstentions.** The generated objects used `INSUFFICIENT_EVIDENCE` but also supplied a non-`UNKNOWN` operative state, violating the shared result contract. Pydantic rejected both objects. They remain processing, operative-state, and abstention failures; they were not retried or normalized after the fact.

### Amendment-chain failures

- **A05** failed because the operative endorsement was not retrieved.
- **A10, C03, C06, C09, C12, and C15** generally produced the correct final policy period but used the original declarations as the initial step instead of reconstructing Rider 17 as the prior operative state. C15 also carried the declarations' inception time into its Rider 18 step. These are genuine chain-history failures even where the final answer is correct.
- **ADV02 and ADV04** correctly abstained but returned partial causal histories, while the frozen expected chain for an unresolved case is empty.
- **ADV01 and ADV03** had no valid chain because their result objects failed validation.

## Interpretation

The baseline reaches the 90% operative-state target exactly and produces fully traceable citations for every valid answer, but it is substantially below the 85% amendment-chain target and the 100% abstention target. Its strongest recurring weakness is the project's central issue: it can often state the final value without reliably preserving the complete sequence of operative amendments and prior states.

This is a credible comparison baseline rather than evidence that the project hypothesis is already proven. Stage 4 must implement the approved explicit provision/relationship model. Stage 5 will then run both systems against the same frozen benchmark and determine whether that model improves these specific failure modes.
