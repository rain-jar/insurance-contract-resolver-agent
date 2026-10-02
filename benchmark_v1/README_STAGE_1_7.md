# Stage 1.7 — Authentic Source Package

This directory is the source package for the Contract Stack Resolver benchmark.

## Status
The four SEC sources and their exact URLs have been verified. The ChatGPT artifact runtime could not fetch the SEC binaries, so the originals are intentionally not fabricated or converted.

## Download
From the `benchmark_v1` directory, run:

```bash
./download_authentic_sources.sh
```

Then verify that these four files exist:

- `documents/authentic/eagle_point/eagle_point_2024_2025_bond.pdf`
- `documents/authentic/jpmorgan/jpmorgan_private_markets_2025_2026_bond.html`
- `documents/authentic/blackrock/blackrock_multi_asset_2024_2025_bond.html`
- `documents/authentic/popular/popular_family_2026_2027_bond.pdf`

`source.json` provenance is stored in `sources.json`. Preserve original SEC formats; do not silently convert HTML filings into PDFs.
