// Fuzzy matching for the composer @/ popovers. A query matches a candidate when
// its characters appear IN ORDER (a subsequence), so "/admcp" still finds
// "add-mcp" and "@chrt" finds "chart". fuzzyScore returns a rank — lower is
// better (prefix < substring < subsequence) — or null for no match. Callers drop
// the nulls and sort ascending, so the closest matches lead.

export function fuzzyScore(query: string, target: string): number | null {
  const q = query.toLowerCase();
  const t = target.toLowerCase();
  if (!q) return 0; // empty query matches everything, no reordering
  if (t.startsWith(q)) return 0; // best: a real prefix
  const idx = t.indexOf(q);
  if (idx >= 0) return 1 + idx / 100; // contiguous substring, earlier wins
  // subsequence: every query char, in order, somewhere in the target
  let qi = 0;
  let first = -1;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) {
      if (first < 0) first = ti;
      qi++;
    }
  }
  return qi === q.length ? 10 + first / 100 : null;
}

/** Keep only items whose key fuzzy-matches `query`, best matches first. */
export function fuzzyFilter<T>(query: string, items: readonly T[], key: (t: T) => string): T[] {
  return items
    .map((item) => ({ item, score: fuzzyScore(query, key(item)) }))
    .filter((x): x is { item: T; score: number } => x.score !== null)
    .sort((a, b) => a.score - b.score)
    .map((x) => x.item);
}
