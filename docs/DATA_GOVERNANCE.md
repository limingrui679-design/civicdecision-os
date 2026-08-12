# Data governance

## Source admission checklist

A source enters the connector registry only after documenting the official publisher, landing
page, machine endpoint, access method, license or public-domain status, required attribution,
update cadence, geographic coverage, temporal coverage, row semantics, known revisions,
personal-data risk, and redistribution boundary.

## Storage classes

| Class | Content | Git policy | Expected control |
|---|---|---|---|
| Public fixture | Small lawful aggregate sample | Allowed with manifest | Hash, license, scope, limitation |
| Public bulk | Large rebuildable public data | Manifest only | Object storage, retention, rebuild test |
| Restricted | Licensed or access-controlled data | Never by default | Separate authorization and storage |
| Personal/sensitive | Direct or indirect identifiers | Prohibited in this public project | Privacy and ethics review required |
| Synthetic | Generated stress-test input | Allowed when labeled | Generator, seed, non-real disclaimer |
| Proposed | Planning parameters and hypothetical actions | Allowed when labeled | Assumptions and reversal tests |

## Lineage invariants

- Preserve raw response bytes before normalization.
- Use namespaced SHA-256 digests for artifacts and schema fingerprints.
- Record exact query parameters, page offsets, and declared limits.
- Distinguish retrieval time from upstream update time.
- Do not silently replace a revised artifact under an old manifest.
- Make page counts additive only when pages are disjoint and deduplicated.
- Publish missingness, schema drift, and quality failures beside successful outputs.

## Interpretation safeguards

Aggregate prevalence is not an individual record. Prediction is not causation. Geographic
association is not an intervention effect. Public records are not proof of service delivery.
Model outputs must preserve uncertainty, limitations, and the source-to-output transformation.

## Retention and removal

Committed fixtures should be minimal. If an upstream license changes, a privacy problem is found,
or removal is required, remove the artifact from future releases, retain a non-sensitive tombstone
manifest when lawful, and document affected DecisionPacks. Git history remediation is a separate
security operation and must be handled explicitly.
