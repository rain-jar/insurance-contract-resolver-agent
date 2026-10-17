# Decision Log

## 2026-10-16 - Bounded relationship retrieval and complete-AMEND chain root

An approved third-system ablation adds one bounded relationship-driven retrieval round to the amendment-aware resolver. It reuses top-eight retrieval and initial extraction, adds at most two relationship-relevant chunks, makes at most one additional extraction call, and leaves provenance and abstention rules unchanged. The completed run made five additional calls and recovered the missing Rider 17 in every targeted contract stack.

The run exposed a chain-output distinction: a complete first `AMEND` establishes a new operative state even though the earlier base remains necessary for ordering and provenance. The approved deterministic correction begins the reported operative chain at such an amendment while retaining the base in reduction and evidence. It does not apply to partial amendments or replacement-style operations.

Deterministic replays produced 90% Operative State, 80% Amendment Chain, 92% Evidence, 100% Abstention, and 100% provenance for the fixed-top-eight resolver; and 96.67% Operative State, 96.67% Amendment Chain, 96% Evidence, 100% Abstention, and 100% provenance for the relationship-driven resolver. The benchmark remained frozen and no new API calls were used for the replays. A05 is the sole remaining substantive failure.

## 2026-10-16 - Equivalent base-event fix and deterministic replay

The completed initial resolver evaluation exposed a deterministic false conflict: the extraction model sometimes represented the same base policy period twice using the broker risk details and declarations labels. The reducer now coalesces `BASE` events only when document, attribute, subject, operation, and normalized value are identical. It merges evidence and prefers a label explicitly referenced by another extracted event. Different values remain distinct, preserving genuine conflict abstention.

The initial API-backed run remains unchanged. Its saved extractions were replayed through the corrected reducer in a separate derived run, avoiding new model variance. Final replay metrics are 90% Operative State, 92% Evidence, 76.67% Amendment Chain, 100% Abstention, and 100% Citation Provenance. The resolver improves chain accuracy and abstention over direct RAG but does not meet the 85% chain target because Rider 17 is repeatedly absent from the shared top-eight retrieval.

## 2026-10-16 - Stage 5 evidence evaluation and interrupted initial run

Stage 5 uses a deterministic Evidence Accuracy rubric rather than a separate rubric-based LLM evaluator. The metric covers the 25 frozen `ANSWER` cases and requires provenance-valid citations, the expected effective source, a citation at the returned effective-source locator, and quoted support for each normalized expected-value component. Abstention evidence is evaluated separately through Abstention Accuracy. Rescoring the preserved Stage 3 baseline produces 24/25 (96%) Evidence Accuracy; A05 fails because its operative endorsement was not retrieved.

The initial resolver benchmark run exhausted the API credit balance after A09. A01–A09 are valid preserved results; A10 through C07 contain external `RateLimitError` records, and later cases were not attempted. This interrupted partial summary is not a benchmark result. Resume behavior now archives retryable external-error records before replacing them, while reusing successful cases and retaining non-retryable model or validation failures as results.

## 2026-10-16 - Stage 4 resolver boundary implemented

The amendment-aware resolver uses one structured `gpt-6.1-sol` extraction call over the same top-eight retrieved chunks used by the baseline. The model may identify provision events, operations, values, source metadata, required references, and explicit supersession, but it does not select the operative answer.

Ordinary deterministic code validates extraction provenance, builds ordering relationships, rejects missing references and unresolved overlapping changes, orders the events, merges partial amendments, and produces the final `ResolutionResult`. Extracted events and relationships remain visible beside the answer. No relationship-driven retrieval expansion is used in Stage 4 because the approved experiment requires both systems to share retrieved evidence.

## 2026-10-15 - Baseline prompt aligned with frozen benchmark assumptions

The first full baseline pass was preserved under `artifacts/stage3_baseline/20261015_gpt-6.1-sol_medium_standard_run1`. Its failure analysis showed that the model rejected controlled amendments because they were labeled synthetic and declined to use endorsement numbering as ordering evidence.

That behavior contradicted frozen assumptions A1 and A5 in `benchmark_v1/HANDOFF_TO_CODEX.md`: endorsement/rider numbers may provide ordering information, and clearly labeled synthetic controlled amendments are valid benchmark material. The direct-RAG prompt was corrected to state those assumptions. This does not add a provision ledger, relationship edges, a deterministic reducer, or relationship-driven retrieval. Run 1 remains unchanged; a clean run 2 will be the Stage 3 baseline result.

## 2026-10-15 - Stage 3 generation model selected

The Stage 3 generation model is locked to `gpt-6.1-sol` for both experimental systems, with medium reasoning effort, standard reasoning mode, and the Standard (`default`) service tier. The request uses a 25,000-token output ceiling for the initial smoke test; the ceiling may be reduced only after observing real reasoning-token usage without causing incomplete responses.

Every API-backed result must record the requested and returned model identifiers, requested and returned service tiers, reasoning configuration, UTC completion time, and token-usage breakdown. Direct RAG and the amendment-aware resolver must use the same generation configuration during comparative evaluation.

## 2026-10-15 - Evidence evaluation remains unresolved

Deterministic citation-provenance validation is approved for Stage 3: every citation must resolve to a supplied document and its quoted text must be traceable to retrieved evidence.

A separate rubric-based LLM evaluator for semantic evidence accuracy is **not approved yet**. It must not block Stage 3 baseline development. Revisit this before Stage 5 comparative evaluation, including alternatives, judge variance, manual spot-checking, and how judge outputs would remain separate from frozen ground truth.
