# Tier-D city and source selection method

Select eight U.S. cities with official bounded 2025 service-request data across Socrata, CKAN DataStore, and CARTO SQL; require four reconciled privacy-minimized aggregate views, an exact Census incorporated-place population row and legal boundary, and a complete six-parameter NASA POWER point series.

The reference layer intentionally exercises three municipal query platforms: six Socrata cities, one CKAN DataStore city, and one CARTO SQL city. This is a reproducibility and schema-heterogeneity choice, not a claim of U.S. or global representativeness.

| # | City | Municipal platform | Official local dataset | Request semantics |
|---:|---|---|---|---|
| 1 | New York City | socrata | `erm2-nwe9` | One NYC 311 service-request record |
| 2 | Boston | ckan-datastore | `9d7c2214-4709-478a-a2e8-fb2020a5bb94` | One legacy BOS:311 service-request record in the 2025 resource |
| 3 | Chicago | socrata | `v6vf-nfxy` | One Chicago 311 service-request record |
| 4 | San Francisco | socrata | `vw6y-z8j6` | One SF311 case record |
| 5 | Seattle | socrata | `5ngg-rpne` | One selected public customer-service-request record |
| 6 | Austin | socrata | `xwdj-i9he` | One Austin 311 service-request record |
| 7 | Los Angeles | socrata | `h73f-gn57` | One MyLA311 2025 service-request record |
| 8 | Philadelphia | carto-sql | `public_cases_fc` | One Philly311 service or information request |

## Required context for every city

- Exact 2024 ACS five-year B01003 incorporated-place population row with 90% MOE.
- Exact current TIGERweb incorporated-place legal boundary GEOID.
- Complete 2025-04-01 through 2025-09-30 NASA POWER point series for six parameters.
- Four independent privacy-minimized municipal aggregates that reconcile to one underlying request total.
