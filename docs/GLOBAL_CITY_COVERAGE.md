# Global city coverage audit

## What is verified

The Tier-G build selects exactly 250 unique populated-place records from the committed GeoNames
`cities15000.zip` artifact. The source ZIP and manifest are verified before parsing. The build then
writes four deterministic artifacts:

| Artifact | Auditable contents |
|---|---|
| `cities-tier-g.json` | Selection algorithm, complete source manifest, 250 city records, source fields, and limitations |
| `cities-tier-g.coverage.csv` | One human-auditable row per selected city |
| `cities-tier-g.semantic.json` | 244 country/territory identities plus 250 city identities |
| `cities-tier-g.graph.json` | 494 nodes and 250 observed `located-in` edges |

`SHA256SUMS` records portable hashes for all four artifacts. The repository verifier builds the
same outputs in a fresh temporary directory and rejects any byte difference.

## Deterministic selection method

1. Validate the ZIP size, member count, member name, traversal safety, CRC, UTF-8 encoding, and
   the 19-column GeoNames row contract.
2. Parse all 34,086 populated-place records and require their count and SHA-256 to match the source
   manifest.
3. Sort records by descending GeoNames source population, then ascending GeoNames identifier as a
   deterministic tie-breaker.
4. Select the first record for every country or territory code represented in the source.
5. Fill remaining positions from the same global order, excluding already selected records.
6. Assign contiguous ranks 1 through 250 and preserve the selection basis for every row.

The resulting catalog has 244 `country-leader` rows and six `global-fill` rows, representing 244
two-letter source codes and 243 IANA timezones. One selected source record has a population value
of zero; it remains visible rather than being silently removed or imputed.

## Claim boundary

- A GeoNames point is not an official municipal polygon.
- Source population values can use different reference years and definitions.
- GeoNames country codes may include territories; the catalog does not define sovereignty.
- Geographic breadth is prioritized before additional high-population cities.
- Tier G means identity and catalog discoverability, not standardized or deep analytical readiness.
- The 34,086 source rows are gazetteer records, not independent policy outcomes or observations.
- The seed graph proves schema and referential-integrity behavior; it is not a production-scale
  urban knowledge graph.

## Rebuild and inspect

```bash
civicdecision cities build-global \
  --manifest examples/data/geonames/geonames-cities15000-98bc5fbd4deb.manifest.json \
  --target-count 250 \
  --output catalog/global-cities

python scripts/verify_repository.py \
  --report verification/milestone-2-global-cities.json
```

The machine-readable report records the catalog content hash, selected-city count, represented
codes, selection-basis counts, timezone count, zero-population count, semantic and graph sizes,
and whether an independent rebuild exactly matched the committed artifacts.
