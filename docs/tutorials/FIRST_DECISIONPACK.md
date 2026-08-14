# Build your first DecisionPack

This tutorial reproduces the committed Suffolk County heat-access reference pair. The completed
configuration and the deliberately infeasible configuration use the same bounded public-data
sample, so you can inspect both release paths without downloading new data.

## 1. Prepare the repository

```bash
git clone https://github.com/limingrui679-design/civicdecision-os.git
cd civicdecision-os
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## 2. Compile the evidence-satisfied run

```bash
civicdecision demo heat-access \
  --data examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.json \
  --manifest examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.manifest.json \
  --scenario examples/scenarios/suffolk-heat-access-demo.yaml \
  --config examples/configs/suffolk-heat-access-default.yaml
```

The committed reference run evaluates 55 bounded tract-centroid combinations and finds 16
feasible under the declared constraints. Its selected bounded option covers an estimated proxy
of 3,121.507 people at a 0.963518788 overall coverage rate.

Validate the generated contract:

```bash
civicdecision protocol validate decision-pack \
  examples/outputs/suffolk-heat-access/decision-pack.json
```

Expected committed content hash:

```text
sha256:909e6c26c686ef688bca83073438c49b79d4b412069dbcb8682c1e8d70ed372b
```

## 3. Inspect the evidence layers

Open the [decision brief](https://github.com/limingrui679-design/civicdecision-os/blob/main/examples/outputs/suffolk-heat-access/decision-brief.md)
and check that each result keeps its type:

| Evidence type | What the reference run contains | What it cannot establish |
|---|---|---|
| Observed | 10 parsed rows from a verified public-data artifact | Individual demand or outcomes |
| Estimated | 3,239.695 people in an area-level need proxy | A person-level service population |
| Simulated | Straight-line coverage at a declared radius | Network travel time or access |
| Optimized | Exhaustive comparison of bounded candidate combinations | Municipal approval or adoption |
| Proposed | Tract centroids used as candidate points | Verified, operable facilities |

## 4. Reproduce a negative release

```bash
civicdecision demo heat-access \
  --data examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.json \
  --manifest examples/data/cdc-places/cdc-places-7ccf6e7d6dc3.manifest.json \
  --scenario examples/scenarios/suffolk-heat-access-demo.yaml \
  --config examples/configs/suffolk-heat-access-infeasible.yaml
```

The committed negative run evaluates 10 combinations, finds zero feasible, records the reason,
and leaves the selected option empty. Compare it with
`examples/outputs/suffolk-heat-access-infeasible/decision-brief.md`.

## 5. Review reversal sensitivity

The completed reference run tests five service radii. Three tests change the selected bounded
option. Treat that as assumption sensitivity—not as a forecast that a real decision will reverse.

Before using the pattern with another decision, replace the proxy, candidate, cost, capacity,
equity, and travel assumptions with versioned evidence reviewed by the responsible domain owner.
