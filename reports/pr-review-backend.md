# PR Review: Go Backend

**Reviewer:** Code Review Agent (Go Backend)
**Range:** 639f366..380d9bb
**Scope:** api/

---

### Strengths

1. **Clean layered architecture.** The code is well-separated into four internal packages (`db`, `embeddings`, `forge`, `handler`) plus a thin `main.go` entry point. Each package has a single, well-defined responsibility. The dependency graph flows downward: `handler -> db, embeddings, forge -> (stdlib)` with no circular imports.

2. **SQL injection protection throughout.** Every SQL query uses parameterised `?` placeholders. The dynamic IN clause in `thesaurus.go:140-156` correctly builds `?` placeholders as strings and passes values via `args ...interface{}` -- never interpolating user input into the query string.

3. **Mega-query eliminates N+1 problem.** `db.go:280-372` (`GetForgeMatches`) consolidates what was originally a per-candidate loop (GetSynset + GetLemmaForSynset + distance computation per row) into a single CTE-based query that returns candidates, synset details, exact property overlap, and pre-computed centroid BLOBs in one database round-trip. This is a significant performance improvement documented in the commit history (`174f6b2`).

4. **Distance normalisation is well-reasoned.** `forge.go:70-98` (`NormaliseDistances`) addresses a real problem: shared-property discovery biases candidates toward similar centroids, causing absolute distances to cluster in a narrow range. Min-max normalisation within the result set ensures tier classification is relative and meaningful. The edge cases (empty, single-element, uniform distances) are handled and tested.

5. **Comprehensive test coverage.** 49 tests cover all four packages, including edge cases (empty vectors, OOV embeddings, nonexistent lemmas, zero vectors, opposite vectors), integration tests against the real SQLite database, and HTTP handler tests using `httptest.NewRecorder`. The tests verify actual data properties (e.g., "fire" has 21 senses, "melancholy" sense 8067 includes "somber"/"sombre") rather than just checking for non-nil returns.

6. **Directory traversal protection.** `handler.go:192-197` applies `filepath.Clean` and checks for `..` sequences, with a dedicated test (`strings_test.go:64-88`) that verifies multiple traversal attack vectors including URL-encoded variants.

7. **Graceful v1/v2 database compatibility.** `db.go:111-122` checks for the `property_similarity` table at runtime and falls back to the legacy exact-match implementation when running against an older database schema.

8. **Input validation with sensible defaults.** `handler.go:70-87` validates threshold (0-1 range) and limit (1-200 range) query parameters, silently falling back to defaults for invalid values rather than returning errors. This is tested explicitly in `handler_test.go:161-215`.

---

### Issues

#### Critical (Must Fix)

None identified. No security vulnerabilities, data loss risks, or broken functionality were found. All 49 tests pass. `go vet` reports no issues.

#### Important (Should Fix)

**I1. Missing `rows.Err()` checks in three functions.** Three row-iteration loops silently discard errors from `rows.Err()` after the loop. If the database connection drops or a row scan fails mid-iteration, the error is lost and a partial result is returned as if it were complete.

- `db.go:82-89` (`GetSynset`, property loop) -- no `rows.Err()` check after line 88
- `db.go:198-224` (`getSynsetsWithSharedPropertiesLegacy`, match loop) -- no `rows.Err()` check after line 224
- `embeddings.go:110-119` (`getSynsetPropertyEmbeddings`, embedding loop) -- no `rows.Err()` check after line 118

This is contrasted with `GetSynsetsWithSharedProperties` (line 165), `GetForgeMatches` (line 367), `querySenses` (line 129), and `queryRelations` (line 182) which all correctly check `rows.Err()`. The inconsistency suggests these were missed rather than deliberately omitted.

**Fix:** Add `if err := rows.Err(); err != nil { return nil, fmt.Errorf("...") }` after each of these three loops.

---

**I2. Silent `continue` on scan errors loses diagnostic information.** Multiple row-scanning loops use `continue` to silently skip rows that fail to scan:

- `db.go:84-85` (property scan in `GetSynset`)
- `db.go:159-160` (match scan in `GetSynsetsWithSharedProperties`)
- `db.go:200-201`, `205-206` (scan and JSON unmarshal in legacy function)
- `db.go:345-346` (scan in `GetForgeMatches`)
- `embeddings.go:112-113` (blob scan in `getSynsetPropertyEmbeddings`)

While silently skipping a single malformed row is a reasonable degraded-mode strategy, there is no logging or metrics to surface the problem. In a production context, a schema migration that changes a column type could cause every row to fail, returning empty results without any indication of the root cause.

**Fix:** At minimum, add a `log.Printf` or structured logger call on the `continue` branches so scan failures are observable. Alternatively, consider returning an error after a configurable threshold of consecutive failures.

---

**I3. `Rarity` and `Metonyms` struct fields are declared but never populated.** `db.go:22` declares `Metonyms []string` and `db.go:26` declares `Rarity string` in the `Synset` struct, but `GetSynset` (line 43-90) never queries or populates these fields. The `json:"...,omitempty"` tags mean they will be absent from JSON output, so this is not a correctness bug, but it adds confusion: a consumer reading the struct definition will expect these fields to be available.

**Fix:** Either remove the fields until the data source exists (SUBTLEX-UK for rarity, SyntagNet for metonyms), or add a comment explaining they are placeholders for Phase 2/3.

---

**I4. Float32 precision loss in `CosineDistance`.** `embeddings.go:58`:
```go
dot += float64(a[i] * b[i])
```
The multiplication `a[i] * b[i]` is performed in `float32` precision before promotion to `float64`. For FastText 300-dimensional embeddings with typical value ranges this is unlikely to cause observable errors, but the fix is trivial:
```go
dot += float64(a[i]) * float64(b[i])
```
The same pattern appears for `normA` (line 59) and `normB` (line 60).

**Why it matters:** Accumulated float32 rounding over 300 dimensions could in theory produce incorrect tier classifications for borderline cases.

---

**I5. Thesaurus lookup query is slow (~1-2 seconds).** The test output shows `TestLookupEndpoint` taking 2.35s and `TestGetLookup_CaseInsensitive` taking 5.74s (for 4 lookups). The root cause is likely the lack of indexes on the `lemmas.lemma` column in the SQLite database combined with the GROUP_CONCAT + LEFT JOIN query in `thesaurus.go:88-97`.

**Why it matters:** The PRD specifies "always under 100ms" for search results. At 1-2 seconds per lookup, this is 10-20x slower than the target.

**Fix:** Ensure the SQLite database has `CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas(lemma)`. This is a database concern rather than a code concern, but the code could verify the index exists on startup or document the requirement.

#### Minor (Nice to Have)

**M1. `GetSynsetIDForLemma` prefers `synset_properties` join but plan specified `enrichment` join.** The sprint zero plan (Task 1, Step 1.3, line 270-276) shows the preference query joining on the `enrichment` table. The implementation (`db.go:380-386`) joins on `synset_properties` instead. Both achieve the goal of preferring enriched synsets, but `synset_properties` is more correct since a synset could have entries in the junction table without having full enrichment metadata. This is actually an improvement over the plan.

**M2. Bubble sort in legacy fallback.** `db.go:228-234` uses a bubble sort (O(n^2)) for the legacy path. Since Go's `sort` package is available and already imported in `forge.go`, using `sort.Slice` would be cleaner and faster for large result sets. However, this is a legacy compatibility path that will rarely be exercised, so the impact is minimal.

**M3. `go 1.22` in `go.mod` but plan says `Go 1.21+`.** `go.mod:3` specifies `go 1.22` with `toolchain go1.22.5`. This is fine -- it just means the minimum Go version is slightly higher than documented.

**M4. Unused `ComputeSynsetDistance` function.** `embeddings.go:75-94` (`ComputeSynsetDistance`) queries property embeddings on-the-fly to compute distance between two synsets. After the mega-query refactor (`GetForgeMatches`), centroid BLOBs are returned directly from the database and distance is computed in the handler using `CosineDistance` on the pre-fetched centroids. `ComputeSynsetDistance` is only used in its own test. It could be removed or marked as a public utility.

**M5. CORS middleware only allows a single origin.** `handler.go:216-231` sets `Access-Control-Allow-Origin` to a single configurable origin. This is correct for development (Vite dev server on port 5173) but the production deployment will need either a list of origins or a more flexible policy. The `--cors-origin` flag in `main.go:18` makes this configurable, which is adequate for now.

**M6. `HandleStrings` hardcodes `en-GB` locale.** `handler.go:202` maps `ui.ftl` to `ui.en-GB.ftl`. When additional locales are needed, this will need a locale negotiation mechanism (Accept-Language header or query parameter). For MVP with UK English only, this is fine.

---

### Recommendations

1. **Add a database startup check.** The handler currently fails with a generic SQLite error if the database file does not exist or lacks expected tables. A startup validation (checking for required tables: `synsets`, `lemmas`, `synset_properties`, `property_vocabulary`, `synset_centroids`) would give much better error messages during deployment.

2. **Consider connection pooling configuration.** The `sql.Open` call returns a `*sql.DB` which manages a connection pool, but SQLite in WAL mode with a single reader needs `SetMaxOpenConns(1)` for correctness. Since the database is opened read-only (`?mode=ro`), concurrent reads should work, but explicitly setting `SetMaxOpenConns` would make the intent clear.

3. **Add request timeouts.** The `http.ListenAndServe` call in `main.go:48` uses the default server which has no read/write timeouts. A slow client could hold connections indefinitely. Use `http.Server{ReadTimeout: 10*time.Second, WriteTimeout: 30*time.Second}` instead.

4. **Structured logging.** The current codebase uses `fmt.Printf` for startup messages, `middleware.Logger` (chi) for request logging, and `log.Fatal` for the server. Consider adopting `log/slog` (available since Go 1.21) for structured, levelled logging that would help with the scan-error observability issue (I2).

---

### Assessment

**Ready to merge?** Yes, with fixes

**Reasoning:** The backend is architecturally sound, well-tested (49 tests, all passing, `go vet` clean), and implements all Sprint Zero requirements. The mega-query approach, distance normalisation, and tiered classification are well-designed. The two substantive issues (I1: missing `rows.Err()` checks, I2: silent scan error swallowing) are defensive-coding gaps that could mask problems in production but do not affect current correctness. I3 (dead struct fields) and I4 (float32 precision) are low-risk. Recommended approach: fix I1 and I2 in a follow-up commit before deploying to production; the rest can be addressed during Phase 1 frontend integration.
