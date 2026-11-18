#!/usr/bin/env bash
# Deduplicate the full author mobility CSV.
# Rows are sanitized (no embedded tabs/newlines), so byte-identical duplicate
# lines are exactly the cross-updated_date-partition repeats.  sort -u removes
# them; because column 1 is author_id, the result is also grouped by author,
# which the aggregation step relies on.
set -euo pipefail

IN="${1:?usage: s21_dedupe_works_mobility.sh <input.csv> <output.csv> [tmpdir]}"
OUT="${2:?usage: s21_dedupe_works_mobility.sh <input.csv> <output.csv> [tmpdir]}"
TMP="${3:-/data2/openAlex/sort_tmp}"

mkdir -p "$TMP"
echo "[dedupe] header"
head -n 1 "$IN" > "$OUT"
echo "[dedupe] sorting/uniquing body -> $OUT"
tail -n +2 "$IN" | LC_ALL=C sort -u -S 120G --parallel 48 -T "$TMP" >> "$OUT"
echo "[dedupe] done: $(wc -l < "$OUT") lines"
