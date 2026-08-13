from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from civicdecision.api import create_app
from civicdecision.product.models import ProductTier, ScenarioKind, ScenarioStatus
from civicdecision.product.store import ArtifactStore
from civicdecision.scenario_library import DecisionType, ImplementationStatus
from civicdecision.sdk import (
    AsyncCivicDecisionClient,
    CivicDecisionClient,
    CivicDecisionSDK,
    SDKHTTPError,
)

ROOT = Path(__file__).parents[1]


class _SyncASGITransport(httpx.BaseTransport):
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        async def send() -> tuple[int, dict[str, str], bytes]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                response = await client.request(
                    request.method,
                    str(request.url),
                    headers=request.headers,
                    content=request.read(),
                )
                content = await response.aread()
                headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() not in {"content-encoding", "content-length"}
                }
                return response.status_code, headers, content

        status, headers, content = asyncio.run(send())
        return httpx.Response(status, headers=headers, content=content, request=request)


def test_local_sdk_opens_repository_and_exposes_all_resource_families() -> None:
    sdk = CivicDecisionSDK.open(str(ROOT), verify_sources=True)
    assert sdk.summary().exposed_city_records == 258
    assert sdk.cities(tier=ProductTier.DEEP, limit=100).pagination.total == 8
    assert sdk.city("us.tx.austin").city.name == "Austin"
    assert (
        sdk.scenarios(
            kind=ScenarioKind.DEEP_PACK,
            status=ScenarioStatus.INSUFFICIENT_EVIDENCE,
            limit=100,
        ).pagination.total
        == 20
    )
    assert sdk.scenario("tierd.us.tx.austin.11").scenario.recommendation_issued is False
    assert sdk.designs(decision_type=DecisionType.EVALUATE, limit=100).pagination.total == 30
    design = sdk.design("scenario.climate.extreme-heat.cooling-center-network.v1")
    assert design.design.method_claimed is False and design.design.city_bindings == []
    assert sdk.design_families(query="climate.extreme-heat", limit=100).pagination.total == 1
    assert len(sdk.design_family("climate.extreme-heat").designs) == 8
    assert sdk.scenario_library_evidence().design_only_scenarios == 228
    assert sdk.decision_pack("tierd.us.tx.austin.01").scenario_id == "tierd.us.tx.austin.01"
    assert "## Result" in sdk.decision_brief("tierd.us.tx.austin.11")
    assert sdk.sources(query="Austin", limit=100).pagination.total == 5
    assert len(sdk.suites()) == 7
    assert sdk.benchmarks().run_artifacts == 145


def test_local_sdk_accepts_prevalidated_store(product_store: ArtifactStore) -> None:
    sdk = CivicDecisionSDK(product_store)
    assert sdk.store is product_store
    assert sdk.cities(country_code="CI", limit=100).pagination.total == 1


def test_synchronous_http_sdk_validates_every_response_model(
    product_store: ArtifactStore,
) -> None:
    transport = _SyncASGITransport(create_app(store=product_store))
    with CivicDecisionClient("http://testserver", transport=transport) as client:
        assert client.summary().tier_assignments == 288
        assert client.cities(tier=ProductTier.DEEP, query="Austin").items[0].name == "Austin"
        assert client.city("us.tx.austin").city.tier is ProductTier.DEEP
        scenarios = client.scenarios(
            kind=ScenarioKind.DEEP_PACK,
            city_id="us.tx.austin",
            suite="behavioral-policy-equity",
            status=ScenarioStatus.INSUFFICIENT_EVIDENCE,
            query="causal",
        )
        assert scenarios.pagination.total == 1
        assert (
            client.scenario(scenarios.items[0].execution_id).scenario.status
            is ScenarioStatus.INSUFFICIENT_EVIDENCE
        )
        assert (
            client.designs(
                implementation_status=ImplementationStatus.REFERENCE_IMPLEMENTED,
                limit=100,
            ).pagination.total
            == 12
        )
        assert (
            client.design(
                "scenario.climate.extreme-heat.cooling-center-network.v1"
            ).design.decision_type
            is DecisionType.SITE
        )
        assert client.design_families(limit=100).pagination.total == 30
        assert len(client.design_family("climate.extreme-heat").designs) == 8
        assert client.scenario_library_evidence().audit_passed
        assert client.decision_pack("tierd.us.tx.austin.01").status.value == "completed"
        assert "# Austin" in client.decision_brief("tierd.us.tx.austin.11")
        assert client.sources(publisher="Austin", query="daily", limit=100).pagination.total == 2
        assert sum(item.execution_count for item in client.suites()) == 96
        assert client.benchmarks().optimization_tasks == 100


def test_synchronous_sdk_turns_problem_details_into_typed_error(
    product_store: ArtifactStore,
) -> None:
    client = CivicDecisionClient(
        "http://testserver",
        transport=_SyncASGITransport(create_app(store=product_store)),
    )
    with pytest.raises(SDKHTTPError) as captured:
        client.city("unknown.city")
    client.close()
    assert captured.value.status_code == 404
    assert captured.value.request_id
    assert "unknown city" in captured.value.detail
    assert "request" in str(captured.value)


def test_sdk_error_falls_back_to_plain_text_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, text="plain upstream failure", request=request)
    )
    client = CivicDecisionClient("https://example.invalid", transport=transport)
    with pytest.raises(SDKHTTPError, match="plain upstream failure"):
        client.summary()
    client.close()


@pytest.mark.asyncio
async def test_asynchronous_http_sdk_matches_synchronous_surface(
    product_store: ArtifactStore,
) -> None:
    transport = httpx.ASGITransport(app=create_app(store=product_store))
    async with AsyncCivicDecisionClient(
        "http://testserver",
        transport=transport,
    ) as client:
        assert (await client.summary()).source_artifacts == 90
        assert (await client.cities(tier=ProductTier.DEEP, limit=100)).pagination.total == 8
        assert (await client.city("us.tx.austin")).city.name == "Austin"
        scenarios = await client.scenarios(
            kind=ScenarioKind.REFERENCE_PACK,
            status=ScenarioStatus.INFEASIBLE,
            limit=100,
        )
        assert scenarios.pagination.total == 1
        execution_id = scenarios.items[0].execution_id
        assert (await client.scenario(execution_id)).scenario.kind is ScenarioKind.REFERENCE_PACK
        assert (
            await client.designs(decision_type=DecisionType.DIAGNOSE, limit=100)
        ).pagination.total == 30
        assert (
            await client.design("scenario.climate.extreme-heat.heat-access-gaps.v1")
        ).design.method_claimed is False
        assert (await client.design_families(limit=100)).pagination.total == 30
        assert len((await client.design_family("climate.extreme-heat")).designs) == 8
        assert (await client.scenario_library_evidence()).reference_implemented_designs == 12
        assert (await client.decision_pack(execution_id)).status.value == "infeasible"
        assert "## Result" in await client.decision_brief(execution_id)
        assert (
            await client.sources(source_id="austin-open-data-311-aggregate", limit=100)
        ).pagination.total == 4
        assert len(await client.suites()) == 7
        assert (await client.benchmarks()).historical_replays == 40


@pytest.mark.asyncio
async def test_asynchronous_sdk_raises_typed_remote_error(product_store: ArtifactStore) -> None:
    transport = httpx.ASGITransport(app=create_app(store=product_store))
    client = AsyncCivicDecisionClient("http://testserver", transport=transport)
    with pytest.raises(SDKHTTPError) as captured:
        await client.scenario("unknown.scenario")
    await client.close()
    assert captured.value.status_code == 404
    assert captured.value.detail == "unknown scenario execution: unknown.scenario"
