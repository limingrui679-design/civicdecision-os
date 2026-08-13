"""Typed SDK facades over the local artifact store and versioned HTTP API."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from civicdecision import __version__
from civicdecision.product.models import (
    BenchmarkOverview,
    CatalogSummary,
    CityDetail,
    CityPage,
    ProductTier,
    ScenarioDetail,
    ScenarioKind,
    ScenarioPage,
    ScenarioStatus,
    SourcePage,
    SuiteOverview,
)
from civicdecision.product.store import ArtifactStore
from civicdecision.protocols.decision import DecisionPack


class SDKHTTPError(RuntimeError):
    """The remote API returned a non-success response."""

    def __init__(self, status_code: int, detail: str, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        self.request_id = request_id
        suffix = f" (request {request_id})" if request_id else ""
        super().__init__(f"CivicDecision API returned {status_code}: {detail}{suffix}")


def _params(
    **values: str | int | ProductTier | ScenarioKind | ScenarioStatus | None,
) -> dict[str, str | int]:
    result: dict[str, str | int] = {}
    for key, value in values.items():
        if isinstance(value, (ProductTier, ScenarioKind, ScenarioStatus)):
            result[key] = value.value
        elif value is not None:
            result[key] = value
    return result


def _error(response: httpx.Response) -> SDKHTTPError:
    detail = response.text
    try:
        payload = response.json()
        if isinstance(payload, dict):
            candidate = payload.get("detail") or payload.get("title")
            if isinstance(candidate, str):
                detail = candidate
    except ValueError:
        pass
    return SDKHTTPError(response.status_code, detail, response.headers.get("x-request-id"))


class CivicDecisionSDK:
    """In-process SDK that validates and reads one immutable repository snapshot."""

    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    @classmethod
    def open(cls, repository_root: str | Path, *, verify_sources: bool = True) -> CivicDecisionSDK:
        return cls(ArtifactStore(repository_root, verify_sources=verify_sources))

    def summary(self) -> CatalogSummary:
        return self.store.summary

    def cities(
        self,
        *,
        tier: ProductTier | None = None,
        query: str | None = None,
        country_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CityPage:
        return self.store.list_cities(
            tier=tier,
            query=query,
            country_code=country_code,
            limit=limit,
            offset=offset,
        )

    def city(self, city_id: str) -> CityDetail:
        return self.store.city_detail(city_id)

    def scenarios(
        self,
        *,
        kind: ScenarioKind | None = None,
        city_id: str | None = None,
        suite: str | None = None,
        status: ScenarioStatus | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScenarioPage:
        return self.store.list_scenarios(
            kind=kind,
            city_id=city_id,
            suite=suite,
            status=status,
            query=query,
            limit=limit,
            offset=offset,
        )

    def scenario(self, execution_id: str) -> ScenarioDetail:
        return self.store.scenario_detail(execution_id)

    def decision_pack(self, execution_id: str) -> DecisionPack:
        return self.store.decision_pack(execution_id)

    def decision_brief(self, execution_id: str) -> str:
        return self.store.decision_brief(execution_id)

    def sources(
        self,
        *,
        source_id: str | None = None,
        publisher: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SourcePage:
        return self.store.list_sources(
            source_id=source_id,
            publisher=publisher,
            query=query,
            limit=limit,
            offset=offset,
        )

    def suites(self) -> list[SuiteOverview]:
        return self.store.suites()

    def benchmarks(self) -> BenchmarkOverview:
        return self.store.benchmark_overview()


class CivicDecisionClient:
    """Synchronous HTTP client for the stable `/api/v1` surface."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={
                "accept": "application/json",
                "user-agent": user_agent or f"civicdecision-python/{__version__}",
            },
            follow_redirects=False,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, *, params: dict[str, str | int] | None = None) -> httpx.Response:
        response = self._client.get(path, params=params)
        if not response.is_success:
            raise _error(response)
        return response

    def summary(self) -> CatalogSummary:
        return CatalogSummary.model_validate(self._get("/api/v1/meta").json())

    def cities(
        self,
        *,
        tier: ProductTier | None = None,
        query: str | None = None,
        country_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CityPage:
        response = self._get(
            "/api/v1/cities",
            params=_params(
                tier=tier,
                q=query,
                country_code=country_code,
                limit=limit,
                offset=offset,
            ),
        )
        return CityPage.model_validate(response.json())

    def city(self, city_id: str) -> CityDetail:
        return CityDetail.model_validate(self._get(f"/api/v1/cities/{city_id}").json())

    def scenarios(
        self,
        *,
        kind: ScenarioKind | None = None,
        city_id: str | None = None,
        suite: str | None = None,
        status: ScenarioStatus | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScenarioPage:
        response = self._get(
            "/api/v1/scenarios",
            params=_params(
                kind=kind,
                city_id=city_id,
                suite=suite,
                status=status,
                q=query,
                limit=limit,
                offset=offset,
            ),
        )
        return ScenarioPage.model_validate(response.json())

    def scenario(self, execution_id: str) -> ScenarioDetail:
        return ScenarioDetail.model_validate(self._get(f"/api/v1/scenarios/{execution_id}").json())

    def decision_pack(self, execution_id: str) -> DecisionPack:
        return DecisionPack.model_validate(
            self._get(f"/api/v1/decision-packs/{execution_id}").json()
        )

    def decision_brief(self, execution_id: str) -> str:
        return self._get(
            f"/api/v1/decision-packs/{execution_id}/brief",
            params={"format": "markdown"},
        ).text

    def sources(
        self,
        *,
        source_id: str | None = None,
        publisher: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SourcePage:
        response = self._get(
            "/api/v1/sources",
            params=_params(
                source_id=source_id,
                publisher=publisher,
                q=query,
                limit=limit,
                offset=offset,
            ),
        )
        return SourcePage.model_validate(response.json())

    def suites(self) -> list[SuiteOverview]:
        return [SuiteOverview.model_validate(item) for item in self._get("/api/v1/suites").json()]

    def benchmarks(self) -> BenchmarkOverview:
        return BenchmarkOverview.model_validate(self._get("/api/v1/benchmarks").json())


class AsyncCivicDecisionClient:
    """Asynchronous HTTP client with the same typed surface as the synchronous client."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={
                "accept": "application/json",
                "user-agent": user_agent or f"civicdecision-python-async/{__version__}",
            },
            follow_redirects=False,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(
        self, path: str, *, params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        response = await self._client.get(path, params=params)
        if not response.is_success:
            raise _error(response)
        return response

    async def summary(self) -> CatalogSummary:
        return CatalogSummary.model_validate((await self._get("/api/v1/meta")).json())

    async def cities(
        self,
        *,
        tier: ProductTier | None = None,
        query: str | None = None,
        country_code: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CityPage:
        response = await self._get(
            "/api/v1/cities",
            params=_params(
                tier=tier,
                q=query,
                country_code=country_code,
                limit=limit,
                offset=offset,
            ),
        )
        return CityPage.model_validate(response.json())

    async def city(self, city_id: str) -> CityDetail:
        return CityDetail.model_validate((await self._get(f"/api/v1/cities/{city_id}")).json())

    async def scenarios(
        self,
        *,
        kind: ScenarioKind | None = None,
        city_id: str | None = None,
        suite: str | None = None,
        status: ScenarioStatus | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ScenarioPage:
        response = await self._get(
            "/api/v1/scenarios",
            params=_params(
                kind=kind,
                city_id=city_id,
                suite=suite,
                status=status,
                q=query,
                limit=limit,
                offset=offset,
            ),
        )
        return ScenarioPage.model_validate(response.json())

    async def scenario(self, execution_id: str) -> ScenarioDetail:
        return ScenarioDetail.model_validate(
            (await self._get(f"/api/v1/scenarios/{execution_id}")).json()
        )

    async def decision_pack(self, execution_id: str) -> DecisionPack:
        return DecisionPack.model_validate(
            (await self._get(f"/api/v1/decision-packs/{execution_id}")).json()
        )

    async def decision_brief(self, execution_id: str) -> str:
        return (
            await self._get(
                f"/api/v1/decision-packs/{execution_id}/brief",
                params={"format": "markdown"},
            )
        ).text

    async def sources(
        self,
        *,
        source_id: str | None = None,
        publisher: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SourcePage:
        response = await self._get(
            "/api/v1/sources",
            params=_params(
                source_id=source_id,
                publisher=publisher,
                q=query,
                limit=limit,
                offset=offset,
            ),
        )
        return SourcePage.model_validate(response.json())

    async def suites(self) -> list[SuiteOverview]:
        response = await self._get("/api/v1/suites")
        return [SuiteOverview.model_validate(item) for item in response.json()]

    async def benchmarks(self) -> BenchmarkOverview:
        return BenchmarkOverview.model_validate((await self._get("/api/v1/benchmarks")).json())


__all__ = [
    "AsyncCivicDecisionClient",
    "CivicDecisionClient",
    "CivicDecisionSDK",
    "SDKHTTPError",
]
