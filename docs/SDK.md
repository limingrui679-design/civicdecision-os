# Python SDK

The SDK provides three typed entry paths over one model set.

## Local repository client

Use the local client when the committed repository snapshot is available:

```python
from pathlib import Path

from civicdecision.product import ProductTier, ScenarioKind, ScenarioStatus
from civicdecision.scenario_library import DecisionType, ImplementationStatus
from civicdecision.sdk import CivicDecisionSDK

sdk = CivicDecisionSDK.open(Path("."), verify_sources=True)

summary = sdk.summary()
deep_cities = sdk.cities(tier=ProductTier.DEEP, limit=100)
negative = sdk.scenarios(
    kind=ScenarioKind.DEEP_PACK,
    status=ScenarioStatus.INSUFFICIENT_EVIDENCE,
    limit=100,
)
designs = sdk.designs(
    decision_type=DecisionType.EVALUATE,
    implementation_status=ImplementationStatus.DESIGN_ONLY,
    limit=100,
)
design = sdk.design("scenario.climate.extreme-heat.heat-access-gaps.v1")
family = sdk.design_family("climate.extreme-heat")
library_evidence = sdk.scenario_library_evidence()
```

`CivicDecisionSDK.open` accepts either a `pathlib.Path` or a string path and normalizes both to a
resolved repository root before validation.

`verify_sources=True` checks committed source artifacts against their manifests before exposing
the snapshot. Turning it off is intended for narrowly scoped diagnostics, not final verification.

## Synchronous HTTP client

```python
from civicdecision.sdk import CivicDecisionClient

with CivicDecisionClient("http://127.0.0.1:8000") as client:
    city = client.city("us.tx.austin")
    design = client.design("scenario.climate.extreme-heat.cooling-center-network.v1")
    families = client.design_families(limit=100)
    pack = client.decision_pack("tierd.us.tx.austin.01")
    brief = client.decision_brief("tierd.us.tx.austin.01")
```

## Asynchronous HTTP client

```python
import asyncio

from civicdecision.scenario_library import DecisionType
from civicdecision.sdk import AsyncCivicDecisionClient


async def inspect() -> None:
    async with AsyncCivicDecisionClient("http://127.0.0.1:8000") as client:
        sources = await client.sources(publisher="City of Austin", limit=100)
        suites = await client.suites()
        designs = await client.designs(decision_type=DecisionType.STRESS_TEST, limit=100)
        audit = await client.scenario_library_evidence()
        benchmark = await client.benchmarks()
        print(
            sources.pagination.total,
            len(suites),
            designs.pagination.total,
            audit.audit_passed,
            benchmark.run_artifacts,
        )


asyncio.run(inspect())
```

## Available methods

All three clients expose summary, city collection/detail, scenario-execution collection/detail,
scenario-design collection/detail, design-family collection/detail, scenario-library evidence,
DecisionPack, DecisionPack brief, source collection, suite overview, and benchmark overview
methods. HTTP clients validate each response against the same Pydantic models used by the local
store; malformed or drifted payloads fail during client-side validation.

Remote non-success responses raise `SDKHTTPError`, retaining the HTTP status, problem detail, and
request ID when present. The default user-agent includes the installed CivicDecision version and
may be overridden explicitly.

## Stability boundary

The versioned HTTP path and product models are the public product contract for this milestone.
The raw `payload` inside `ScenarioDetail` retains its native source schema and may grow only in a
way consistent with that underlying versioned protocol. Callers must not infer production status,
external validity, or observed impact from successful retrieval.

`designs()` returns design contracts rather than execution results. A
`reference-implemented` design indicates a bounded mapping to an existing Tier-D template, while
`design-only` indicates no current execution. SDK users must preserve that distinction when
creating reports or downstream interfaces.
