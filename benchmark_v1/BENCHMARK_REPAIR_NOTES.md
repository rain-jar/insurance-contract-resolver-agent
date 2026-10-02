# Benchmark Repair Notes

This patch addresses two benchmark-construction issues discovered during Stage 2 exploration.

1. C01–C15 now contain explicit ground-truth `amendment_chain` annotations and case-specific `required_evidence`.
2. C09 is made self-contained as a true partial-amendment stack:
   - its `contract_stack` now includes `controlled_popular_riders_18_19.txt` before Rider 20;
   - Rider 20 no longer contains a benchmark-only precondition asserting Rider 19's state.

No expected final answers were changed.

## Apply

From `benchmark_v1/`:

1. Replace `benchmark/benchmark.json` with this patch's `benchmark.json`.
2. Replace `documents/controlled/controlled_popular_rider_20_partial.txt` with the patched version.
3. Run `python validate_benchmark.py`.
4. Inspect `git diff` before committing.

Suggested commit:
`Fix controlled benchmark chain annotations`
