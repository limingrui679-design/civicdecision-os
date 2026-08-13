# Milestone 4 analytical-engine benchmark audit

Registry content hash: `sha256:8ea10c750993908a89a4ebe92c9605cc61e92df15677ce389213c46ac27a40ad`

- Historical held-out public-data replays: 40
- Synthetic portfolio optimization tasks: 100
- Synthetic engine qualification runs: 5
- Total independently serialized run artifacts: 145
- Training observations across replay tasks: 13,440
- Strictly held-out observations across replay tasks: 1,200
- Optimization search-space portfolios declared: 24,000
- Optimization portfolios actually evaluated: 21,710
- Feasible portfolios encountered: 4,333
- Explicit selected-versus-zero-action baseline comparisons: 70

## Forecast method counts

- `drift`: 2
- `moving-average`: 19
- `naive`: 13
- `seasonal-naive`: 6

## Optimization strategy counts

- `expected`: 50
- `worst-case`: 50

## Status counts

- `completed`: 41
- `identification-passed`: 1
- `infeasible`: 20
- `insufficient-evidence`: 1
- `optimal`: 70
- `reversal-risk`: 1
- `robust-winner`: 1
- `search-limited`: 10

## Claim boundary

The 40 historical replays are held-out tasks over 20 NASA POWER city-point artifacts and two parameters. They are not 40 cities, 40 independent datasets, or live forecasts. The 100 optimization tasks and five method-qualification runs are synthetic software evidence. They do not establish external validity, adoption, users, or impact.
