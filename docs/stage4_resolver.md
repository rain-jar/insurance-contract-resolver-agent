# Stage 4 Contract Stack Resolver

## Status

Stage 4 implementation and representative demonstrations are complete. The resolver is ready for the approval gate before Stage 5 comparative evaluation.

## System boundary

The baseline and resolver receive the same parsed chunks and the same top-eight hybrid retrieval results. Their difference is what happens after retrieval:

1. `gpt-6.1-sol` extracts query-relevant `ProvisionEvent` objects from retrieved evidence.
2. Deterministic provenance validation requires every event quote to occur in the cited retrieved chunk.
3. The resolver constructs explicit precedence relationships from:
   - base-before-amendment status;
   - endorsement or rider numbers;
   - effective dates;
   - explicit references;
   - explicit supersession.
4. A deterministic reducer orders the events, rejects missing references or unresolved precedence, merges partial amendments, and emits the shared `ResolutionResult` contract.

The extraction model does not choose the final operative value. The reducer does not infer provisions absent from extracted, traceable evidence.

## Representation

Each provision event records:

- supported attribute and subject;
- operation (`BASE`, `ADD`, `AMEND`, `REPLACE`, `DELETE_AND_RESTATE`, `DELETE`, or `SUPERSEDE`);
- full or partial normalized value;
- source path, provision label, and locator;
- exact evidence quotes and extraction method;
- numeric/effective-date ordering metadata;
- required referenced sources;
- explicitly superseded sources.

Relationships retain both endpoints and their basis. Multiple bases may be preserved for one edge: for example, C13 records both `DOCUMENT_NUMBER` and `EXPLICIT_SUPERSESSION` for Endorsement 8 → Endorsement 11.

## Deterministic failure behavior

The resolver returns `INSUFFICIENT_EVIDENCE` with an empty answer chain when:

- a referenced source or schedule required for the operative value is absent;
- replacement-style language does not supply a complete value;
- two provisions modify overlapping fields without sufficient precedence;
- extracted evidence fails provenance validation;
- relationship edges form a cycle;
- or the operative value remains incomplete after reduction.

The raw extracted events and any relationships remain inspectable even when the answer abstains.

## Representative demonstrations

### C01 — numbered delete-and-restate chain

The resolver extracted the $3.5M declarations value, Endorsement 7's $4.25M restatement, and Endorsement 8's $5M restatement. Numeric relationships ordered the amendments, the reducer returned USD 5,000,000, and extraction/result provenance both passed. A narrow label normalizer was added afterward to keep provenance annotations out of provision labels while retaining them in source paths and evidence.

### C09 — partial policy-period amendments

The resolver extracted Rider 18's expiration change, Rider 19's later expiration change, and Rider 20's inception-only change. Deterministic merging preserved Rider 19's 31 December 2027 expiration when Rider 20 replaced only inception, producing 1 March 2027 at noon through 31 December 2027 at noon.

The exact historical chain remained incomplete because Rider 17 was not present in the shared top-eight retrieved evidence. The resolver began from the declarations instead. This is a shared retrieval ceiling, not a deterministic-reducer failure, and must remain visible in Stage 5.

### C13 — explicit supersession

The resolver reconstructed four states: $1.25M declarations, $1.775M Endorsement 2, $3M Endorsement 8, and $2.25M Endorsement 11. It represented both numeric ordering and explicit supersession between Endorsements 8 and 11, then selected USD 2,250,000 with zero provenance errors.

### ADV03 — missing referenced endorsement

The resolver extracted the earlier $3.5M and $4.25M states plus Endorsement 10's dependency on Endorsement 9. Because Endorsement 9 was absent, deterministic code returned `INSUFFICIENT_EVIDENCE` rather than treating $4.25M as current.

### ADV01 — unresolved conflicting replacements

The resolver extracted both unnumbered $5M and $6M replacement amendments. Because no number, date, reference, or supersession established precedence, deterministic code returned `INSUFFICIENT_EVIDENCE` with an empty answer chain.

## Verification

- 21 automated tests pass.
- The frozen benchmark validator passes all 30 cases.
- The benchmark was not modified.
- Demonstrated live cases used `gpt-6.1-sol`, medium reasoning, standard mode, and the Standard service tier.
- No full resolver benchmark was run in Stage 4; that belongs to the approved Stage 5 comparison after this gate.
