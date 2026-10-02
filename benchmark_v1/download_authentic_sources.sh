#!/usr/bin/env bash
set -euo pipefail
UA="ContractStackResolverBenchmark/1.0 research-contact@example.com"
mkdir -p documents/authentic/{eagle_point,jpmorgan,blackrock,popular}
curl -L --fail --retry 3 -A "$UA" 'https://www.sec.gov/Archives/edgar/data/1992148/000110465925069985/tm2521531d1_4017g.pdf' -o documents/authentic/eagle_point/eagle_point_2024_2025_bond.pdf
curl -L --fail --retry 3 -A "$UA" 'https://www.sec.gov/Archives/edgar/data/2056164/000119312525323763/d15570d4017g.htm' -o documents/authentic/jpmorgan/jpmorgan_private_markets_2025_2026_bond.html
curl -L --fail --retry 3 -A "$UA" 'https://www.sec.gov/Archives/edgar/data/97098/000119312525025906/d928362d4017g.htm' -o documents/authentic/blackrock/blackrock_multi_asset_2024_2025_bond.html
curl -L --fail --retry 3 -A "$UA" 'https://www.sec.gov/Archives/edgar/data/1862970/000139834426015733/fp0100636-2_4017g.pdf' -o documents/authentic/popular/popular_family_2026_2027_bond.pdf
printf '\nDownloaded authentic benchmark sources.\n'
