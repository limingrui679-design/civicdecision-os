from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from civicdecision.api import create_app
from civicdecision.product.store import ArtifactStore


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


@pytest.fixture(scope="module")
def product_app(product_store: ArtifactStore) -> FastAPI:
    return create_app(store=product_store)


@pytest.fixture(scope="module")
def api_client(product_app: FastAPI) -> Iterator[httpx.Client]:
    with httpx.Client(
        transport=_SyncASGITransport(product_app),
        base_url="http://testserver",
    ) as client:
        yield client


def test_health_and_readiness_expose_live_catalog_identity(
    api_client: httpx.Client,
    product_store: ArtifactStore,
) -> None:
    health = api_client.get("/healthz")
    ready = api_client.get("/readyz")
    assert health.status_code == ready.status_code == 200
    assert health.json()["status"] == ready.json()["status"] == "ok"
    assert health.json()["catalog_fingerprint"] == ready.json()["catalog_fingerprint"]
    assert health.headers["cache-control"] == "no-store"
    app_from_string = create_app(str(product_store.repository_root), verify_sources=False)
    assert app_from_string.state.store.repository_root == product_store.repository_root


def test_meta_is_typed_cacheable_and_request_correlated(api_client: httpx.Client) -> None:
    response = api_client.get("/api/v1/meta", headers={"x-request-id": "review-12345678"})
    assert response.status_code == 200
    assert response.json()["exposed_city_records"] == 258
    assert response.headers["x-request-id"] == "review-12345678"
    assert response.headers["etag"].startswith('"')
    assert len(response.headers["etag"]) == 66
    assert response.headers["cache-control"] == "public, max-age=60, must-revalidate"


def test_conditional_get_returns_304_only_after_valid_route_resolution(
    api_client: httpx.Client,
) -> None:
    etag = api_client.get("/api/v1/meta").headers["etag"]
    cached = api_client.get("/api/v1/meta", headers={"if-none-match": etag})
    missing = api_client.get("/api/v1/not-a-route", headers={"if-none-match": etag})
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == etag
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")


def test_city_collection_supports_tier_search_country_and_pagination(
    api_client: httpx.Client,
) -> None:
    response = api_client.get(
        "/api/v1/cities",
        params={"tier": "D", "q": "a", "country_code": "us", "limit": 3},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"]["returned"] == 3
    assert all(item["tier"] == "D" and item["country_code"] == "US" for item in payload["items"])


def test_city_detail_and_path_validation_are_fail_closed(api_client: httpx.Client) -> None:
    detail = api_client.get("/api/v1/cities/us.tx.austin")
    invalid = api_client.get("/api/v1/cities/INVALID CITY")
    missing = api_client.get("/api/v1/cities/unknown.city")
    assert detail.status_code == 200
    assert detail.json()["city"]["tier"] == "D"
    assert invalid.status_code == 422
    assert invalid.json()["title"] == "Request validation failed"
    assert missing.status_code == 404
    assert missing.json()["title"] == "Artifact not found"


def test_scenario_collection_exposes_exact_filter_counts(api_client: httpx.Client) -> None:
    cases = [
        ({"kind": "standard-screen"}, 90),
        ({"kind": "deep-pack"}, 96),
        ({"kind": "reference-pack"}, 2),
        ({"status": "completed"}, 77),
        ({"status": "insufficient-evidence"}, 50),
        ({"status": "infeasible"}, 1),
    ]
    for params, expected in cases:
        response = api_client.get("/api/v1/scenarios", params={**params, "limit": 1})
        assert response.status_code == 200
        assert response.json()["pagination"]["total"] == expected


def test_scenario_status_query_rejects_unknown_values(api_client: httpx.Client) -> None:
    response = api_client.get("/api/v1/scenarios", params={"status": "invented"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_scenario_detail_preserves_negative_evidence_boundary(api_client: httpx.Client) -> None:
    response = api_client.get("/api/v1/scenarios/tierd.us.tx.austin.11")
    payload = response.json()
    assert response.status_code == 200
    assert payload["scenario"]["status"] == "insufficient-evidence"
    assert payload["scenario"]["recommendation_issued"] is False
    assert payload["scenario"]["selected_option_id"] is None
    assert payload["claim_boundary"]


def test_decision_pack_collection_and_markdown_brief(api_client: httpx.Client) -> None:
    listing = api_client.get(
        "/api/v1/decision-packs",
        params={"status": "insufficient-evidence", "limit": 100},
    )
    pack = api_client.get("/api/v1/decision-packs/tierd.us.tx.austin.11")
    brief = api_client.get("/api/v1/decision-packs/tierd.us.tx.austin.11/brief")
    assert listing.json()["pagination"]["total"] == 20
    assert pack.status_code == 200 and pack.json()["status"] == "insufficient_evidence"
    assert brief.status_code == 200
    assert brief.headers["content-type"].startswith("text/markdown")
    assert "filename=" in brief.headers["content-disposition"]
    assert "## Result" in brief.text
    assert "insufficient_evidence" in brief.text


def test_standard_screen_cannot_be_promoted_to_decision_pack(api_client: httpx.Client) -> None:
    execution_id = "geonames.2293538.screen.heat.2024"
    response = api_client.get(f"/api/v1/decision-packs/{execution_id}")
    assert response.status_code == 404
    assert "deliberately not a DecisionPack" in response.json()["detail"]


def test_sources_suites_benchmarks_and_deep_evidence_are_consistent(
    api_client: httpx.Client,
) -> None:
    sources = api_client.get("/api/v1/sources", params={"publisher": "Austin", "limit": 100})
    suites = api_client.get("/api/v1/suites")
    benchmark = api_client.get("/api/v1/benchmarks")
    deep = api_client.get("/api/v1/evidence/deep")
    assert sources.json()["pagination"]["total"] == 4
    assert len(suites.json()) == 7
    assert sum(item["execution_count"] for item in suites.json()) == 96
    assert benchmark.json()["run_artifacts"] == 145
    assert deep.json()["city_bound_scenario_executions"] == 96
    assert deep.json()["total_simulation_iterations"] == 190_000


def test_openapi_is_versioned_and_documents_all_product_resources(
    api_client: httpx.Client,
) -> None:
    response = api_client.get("/api/openapi.json")
    document = response.json()
    assert response.status_code == 200
    assert document["info"]["title"] == "CivicDecision OS API"
    assert document["openapi"].startswith("3.")
    assert len(document["paths"]) == 14
    assert "/api/v1/decision-packs/{execution_id}/brief" in document["paths"]
    assert "/docs" not in document["paths"]


def test_web_explorer_and_assets_are_packaged_without_external_runtime_dependencies(
    api_client: httpx.Client,
) -> None:
    page = api_client.get("/")
    css = api_client.get("/assets/app.css")
    javascript = api_client.get("/assets/app.js")
    favicon = api_client.get("/favicon.svg")
    assert (
        page.status_code == css.status_code == javascript.status_code == favicon.status_code == 200
    )
    assert "Urban decisions" in page.text
    assert '<script src="/assets/app.js" defer></script>' in page.text
    assert "https://" not in page.text and "http://" not in page.text
    assert "Content-Security-Policy" in page.headers
    assert page.headers["x-frame-options"] == "DENY"
    assert css.headers["cache-control"] == "public, max-age=3600"
    assert "fetch(" in javascript.text


def test_method_not_allowed_and_missing_routes_use_problem_details(
    api_client: httpx.Client,
) -> None:
    method = api_client.post("/api/v1/meta")
    missing = api_client.get("/missing")
    assert (method.status_code, method.json()["title"]) == (405, "Method not allowed")
    assert (missing.status_code, missing.json()["title"]) == (404, "Route not found")
    assert method.headers["content-type"].startswith("application/problem+json")


def test_request_id_policy_accepts_safe_values_and_replaces_unsafe_values(
    api_client: httpx.Client,
) -> None:
    accepted = api_client.get("/api/v1/meta", headers={"x-request-id": "abcDEF_1234"})
    rejected = api_client.get("/api/v1/meta", headers={"x-request-id": "bad value"})
    assert accepted.headers["x-request-id"] == "abcDEF_1234"
    assert rejected.headers["x-request-id"] != "bad value"
    assert len(rejected.headers["x-request-id"]) == 24
    int(rejected.headers["x-request-id"], 16)


def test_openapi_artifact_matches_runtime_document(api_client: httpx.Client) -> None:
    runtime = api_client.get("/api/openapi.json").json()
    with open("catalog/product/openapi-v1.json", encoding="utf-8") as handle:
        committed = json.load(handle)
    assert runtime == committed
