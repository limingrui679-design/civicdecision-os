# Tier-D anti-inflation audit

| Quantity | Audited count | Counting rule |
|---|---:|---|
| Non-duplicative scenario designs | 12 | Count shared templates once. |
| City-bound scenario executions | 96 | 12 templates x 8 cities; not unique methods. |
| Distinct source datasets | 11 | 8 local datasets plus ACS, TIGERweb, and NASA POWER. |
| Deduplicated source artifacts | 49 | 32 municipal views, 8 boundaries, 8 climate points, 1 shared ACS file. |
| Underlying municipal requests | 4,148,633 | Count each city's reconciled total once. |
| Naive four-view request sum rejected | 16,594,532 | Same requests re-aggregated four ways; never a distinct-request total. |
| Aggregate source rows | 148,836 | Endpoint-side grouped rows, not individual requests. |
| Context source units | 8,800 | 8 ACS rows + 8 boundaries + 8 x 1,098 NASA parameter-date values. |
| Simulation iterations | 190,000 | Computational draws, not observations. |
| Optimization plans evaluated | 237,500 | Mathematical portfolios, not implemented actions. |
| Uncertainty option-draw values | 228,000 | Computational values, not users. |

No count in this audit establishes external review, domain validity, deployment, users, municipal adoption, or real-world impact.
