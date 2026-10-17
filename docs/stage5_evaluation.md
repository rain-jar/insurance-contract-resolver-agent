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

## Preserved runs

The initial resolver run is preserved at:

`artifacts/stage5_resolver/20261016_gpt-6.1-sol_medium_standard_run1`

It completed all 30 cases after resuming from an archived API-credit interruption. Its raw results were 80% Operative State, 76% Evidence, 76.67% Amendment Chain, 100% Abstention, and 100% Citation Provenance.

Failure analysis found that five answer cases plus ADV04 contained two extracted `BASE` events with the same document, attribute, subject, operation, and normalized value but different human-readable labels. The reducer incorrectly treated those duplicate representations as competing changes. The approved fix coalesces only equivalent base events, merges their evidence, and retains a label explicitly referenced by another event. Different values and genuine amendment conflicts remain separate.

The saved extraction events were then replayed through the corrected deterministic reducer without new API calls. The derived run is preserved at:

`artifacts/stage5_resolver/20261016_replay1_equivalent_base_fix`

## Fixed-top-eight comparison after the approved fix

| Metric | Target | Baseline | Resolver replay | Difference |
|---|---:|---:|---:|---:|
| Operative State Accuracy | >= 90% | 27/30 (90.00%) | 27/30 (90.00%) | 0.00 pp |
| Evidence Accuracy | >= 90% | 24/25 (96.00%) | 23/25 (92.00%) | -4.00 pp |
| Amendment-Chain Accuracy | >= 85% | 19/30 (63.33%) | 23/30 (76.67%) | +13.34 pp |
| Abstention Accuracy | 100% | 3/5 (60.00%) | 5/5 (100.00%) | +40.00 pp |
| Citation Provenance Validity | — | 25/25 (100.00%) | 25/25 (100.00%) | 0.00 pp |

The resolver meets the Operative State, Evidence, Abstention, and provenance goals. It improves Amendment-Chain Accuracy substantially over direct RAG but does not meet the 85% chain target.

## Remaining failures

- **A05:** both systems miss the operative Endorsement 2 provision because it is absent from the shared top-eight retrieval.
- **C06 and C12:** Rider 17 is absent from retrieval. Later partial amendments therefore carry forward the base document's 12:01 a.m. inception rather than Rider 17's operative noon inception.
- **A10:** the final answer is correct, but the resolver includes the pre-amendment base in its chain while the frozen chain begins with Rider 17.
- **C03, C06, C09, C12, and C15:** the final chain is incomplete because Rider 17 is absent from the shared retrieved evidence. C03, C09, and C15 still produce the correct final state from later evidence.

C12 illustrates why metrics remain separate: its returned citation contains the benchmark-required noon inception, so Evidence Accuracy passes, but the extracted partial event intentionally leaves unchanged inception null and the reducer carries forward the wrong retrieved prior state. Operative State therefore fails.

## Interpretation

The core hypothesis is partially supported. Explicit relationship modeling improves exact chain reconstruction and safe abstention, while matching baseline operative accuracy after the reducer fix. It does not outperform baseline operative accuracy or Evidence Accuracy under the shared top-eight retrieval ceiling, and it remains below the absolute chain target.

This fixed-top-eight result motivated a separately approved relationship-driven retrieval ablation. Keeping it separate preserves the fairness and auditability of the original baseline comparison.

## Approved third-system ablation

The follow-up system preserves the amendment-aware resolver but permits one bounded relationship-driven retrieval expansion. It reuses the initial top-eight retrieval and extraction, detects explicit-source and cross-document predecessor gaps, adds no more than two relationship-relevant chunks in one round, and makes no more than one additional extraction call. Provenance validation and abstention behavior are unchanged.

The API-backed run is preserved at:

`artifacts/stage5_relationship/20261016_bounded_run1`

Expansion was used for five contract-stack cases. Each added exactly one chunk containing Rider 17, for five additional extraction calls and 10,160 additional total tokens relative to the fixed-top-eight resolver. ADV02 and ADV03 correctly found no qualifying missing source and did not broaden retrieval.

The initial third-system run recovered Rider 17 and improved operative answers, but its reported chains still included the superseded base period. The approved chain-root correction now treats a complete first `AMEND` as the start of the operative amendment chain. The base event remains in deterministic ordering, state reduction, and evidence; partial amendments and replacement-style operations do not trigger this presentation rule.

Both systems were replayed without new API calls. The preserved replay directories are:

- Fixed top eight: `artifacts/stage5_resolver/20261016_replay2_complete_amend_chain_root`
- Relationship-driven: `artifacts/stage5_relationship/20261016_replay1_complete_amend_chain_root`

## Final three-system result

| Metric | Baseline | Fixed top eight | Relationship-driven |
|---|---:|---:|---:|
| Operative State Accuracy | 27/30 (90.00%) | 27/30 (90.00%) | **29/30 (96.67%)** |
| Evidence Accuracy | 24/25 (96.00%) | 23/25 (92.00%) | **24/25 (96.00%)** |
| Amendment-Chain Accuracy | 19/30 (63.33%) | 24/30 (80.00%) | **29/30 (96.67%)** |
| Abstention Accuracy | 3/5 (60.00%) | **5/5 (100.00%)** | **5/5 (100.00%)** |
| Citation Provenance Validity | **25/25 (100.00%)** | **25/25 (100.00%)** | **25/25 (100.00%)** |

The third system clears the approved 85% chain target without reducing operative accuracy, abstention, or provenance. Against the fixed-top-eight resolver it gains 6.67 percentage points in operative accuracy, 16.67 points in chain accuracy, and 4 points in evidence accuracy. Against direct RAG it gains 6.67 points operative, 33.34 points chain, and 40 points abstention while matching evidence and provenance.

A05 is the only remaining substantive failure. Its operative Endorsement 2 is absent from initial retrieval, and the current relationship-gap detector has no extracted clue that justifies expanding toward it within the approved bounds.

The comparison artifacts are preserved under:

`artifacts/stage5_comparison/20261016_relationship_replay1_complete_amend_chain_root`
