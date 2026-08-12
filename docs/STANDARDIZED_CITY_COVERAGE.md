# Tier-S standardized city coverage audit

## Completion contract

A city counts toward Tier S only when all of the following are committed and independently
verified:

1. one Tier-G GeoNames identity record;
2. one NASA POWER point artifact containing all six declared parameters for every day of leap
   year 2024;
3. non-null 2023 World Bank values for all three declared national context indicators;
4. a Tier-S City Adapter with explicit capabilities, data gaps, and limitations;
5. source bindings that keep identity-point, gridded-point, and country-context geography distinct;
6. a quality report with no failed required check and 100% required-value completeness;
7. eleven evidence-typed metrics with exact source references and geographic scope;
8. three independent scenario records with non-duplicative template IDs; and
9. bundle, run, registry, comparison, coverage, and checksum artifacts that rebuild byte-for-byte.

The relevant official API documentation is the [NASA POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)
and the [World Bank V2 Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392).
NASA POWER documents a maximum of 20 parameters for a single point; this project requests six.
The build uses the same UTC time standard, dates, and parameters for every selected city.

## Verified source volume

| Layer | Artifacts | Declared source units | Role |
|---|---:|---:|---|
| GeoNames `cities15000` | 1 shared ZIP | 34,086 gazetteer rows | City identity and source point |
| NASA POWER | 30 GeoJSON responses | 65,880 parameter-date values | 366 days × 6 parameters × 30 points |
| World Bank | 3 shared JSON pages | 795 response rows | Three 2023 national context indicators |

The counts use each connector's documented record semantics. They must not be added together and
described as homogeneous observations or people. GeoNames rows and World Bank aggregates are not
city outcomes; NASA POWER values are gridded analysis-ready products, not station observations.

## Selection and exclusion audit

The compiler scans Tier-G cities in catalog order and selects the first 30 cities that satisfy the
complete source contract. It does not silently impute missing context.

- 30 bundles are selected from Tier-G ranks 1–31.
- Taipei, Tier-G rank 19, is excluded before target completion because all three required World
  Bank 2023 context values are absent for its source country code and no matching standard climate
  artifact was committed after the context pre-screen.
- Jeddah, Tier-G rank 31, is therefore the 30th eligible city.
- Eligibility means source completeness under this protocol, not importance, policy priority,
  representativeness, or institutional readiness.

The registry retains the exclusion and its individual reasons in
[`registry.json`](../catalog/standardized-cities/registry.json). The selected list and bundle hashes
are also available as [`coverage.csv`](../catalog/standardized-cities/coverage.csv).

## Quality gates

Every selected city passes six required checks:

| Check | Required result |
|---|---|
| Parsed value count | Exactly 2,196 values |
| Source-manifest count | Exactly equals the independently parsed count |
| Daily-key alignment | All six parameters share 366 daily keys |
| Fill-value count | Zero `-999` source fill values |
| Response-coordinate rounding | Maximum difference from the request point is at most 0.001 degrees |
| Query-to-catalog point | Exact equality before the source response's coordinate rounding |

Passing these gates establishes completeness and transformation integrity only. It does not prove
that one point represents within-city microclimate or exposure.

## Metrics and scenario records

Each bundle contains eight climate summaries and three national context metrics, for 330 metrics
overall. All are typed `estimated` because they summarize gridded products or aggregate indicators;
none is upgraded to an observed city outcome.

Each city has three independent run files:

| Template | Status per city | What it establishes |
|---|---|---|
| `standard.heat-screen.v1` | `screened` | Descriptive point heat and national urbanization context |
| `standard.precipitation-screen.v1` | `screened` | Descriptive point precipitation/wind and national population context |
| `standard.policy-readiness.v1` | `insufficient-evidence` | The current sources cannot support an intervention choice or outcome claim |

Across 30 cities, that produces 60 screened records and 30 negative evidence releases. The
registry preserves the three template IDs so the 90 city-bound records cannot be misreported as 90
semantically distinct scenario designs. Every record sets `recommendation_issued=false`.

## Cross-city comparison boundary

The generated [Markdown report](../catalog/standardized-cities/cross-city-comparison.md) and
[machine-readable CSV](../catalog/standardized-cities/cross-city-comparison.csv) expose every
selected city and all standardized values. They deliberately contain no composite score or policy
ranking. Cross-city differences can reflect gridded resolution, source methods, country-level
aggregation, and city-point selection; they are not evidence that one city performs better or
should adopt a particular intervention.

## Rebuild

```bash
civicdecision cities build-standardized \
  --catalog catalog/global-cities/cities-tier-g.json \
  --climate-directory examples/data/tier-s/nasa-power \
  --country-context-directory examples/data/tier-s/world-bank \
  --target-count 30 \
  --output catalog/standardized-cities

python scripts/verify_repository.py \
  --report verification/milestone-3-standardized-cities.json
```

The verifier checks the current artifacts and then writes a separate temporary build. File lists,
relative paths, JSON, CSV, Markdown, and recursive checksums must match exactly. A successful local
verification is implementation evidence; it is not remote CI, external review, deployment, user
impact, or policy effectiveness.
