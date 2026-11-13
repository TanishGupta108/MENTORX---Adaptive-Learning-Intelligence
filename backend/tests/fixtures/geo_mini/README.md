Synthetic Geography fixture for `tests/test_geography_seed.py` (no real data; hand-designed).

- `place.csv`: 8 "countries" and 7 "cities" on the Europe map, in the Slepemapy format.
- `geometry/`: squares and points in a 1000-wide viewBox, plus a names.yaml override.
- `artifacts/`: a minimal kt_meta.json (2 skills) and question_stats.json.

Traps the seed must handle: a disputed country (`xk`) and city (`pristina`) that are present in
every file, and listed as the most frequent confusion of every question, yet must never be asked
or offered; Belgium is placed less than 6 % of the map width from France.
