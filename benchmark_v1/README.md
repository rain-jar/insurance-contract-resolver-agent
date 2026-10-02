# benchmark_v1 — Contract Stack Resolver

Frozen benchmark target: 30 independent cases.

- 10 authentic cases grounded in the four public source stacks
- 15 controlled cases using clearly labeled synthetic amendments
- 5 adversarial cases testing abstention / unsupported attributes

Canonical benchmark file: `benchmark/benchmark.json`.

Supported ontology: `LIMIT`, `DEDUCTIBLE`, `POLICY_PERIOD`.
`ADV05` deliberately asks for `TERRITORIAL_COVERAGE` and expects `UNSUPPORTED_ATTRIBUTE`.

## Freeze rule
Do not alter a case because an implementation fails it. Correct genuine annotation/path/data errors only, and document any such correction.

## Validate
From `benchmark_v1/` run:

    python validate_benchmark.py

Expected result: 30 cases, correct type counts, and every referenced document path exists.
