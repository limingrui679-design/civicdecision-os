"""FastAPI application factory backed by the validated artifact store."""

from __future__ import annotations

import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request, Response
from fastapi import Path as PathParameter
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from civicdecision import __version__
from civicdecision.deep.models import TierDEvidenceSummary
from civicdecision.errors import IntegrityError
from civicdecision.product.models import (
    BenchmarkOverview,
    CatalogSummary,
    CityDetail,
    CityPage,
    ProductHealth,
    ProductTier,
    ScenarioDetail,
    ScenarioKind,
    ScenarioPage,
    ScenarioStatus,
    SourcePage,
    SuiteOverview,
)
from civicdecision.product.store import (
    ArtifactStore,
    ProductCatalogError,
    ProductNotFoundError,
)
from civicdecision.protocols.base import IDENTIFIER_PATTERN, StrictModel
from civicdecision.protocols.decision import DecisionPack

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,80}$")


class ProblemDetail(StrictModel):
    type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: int = Field(ge=400, le=599)
    detail: str = Field(min_length=1)
    instance: str = Field(min_length=1)
    request_id: str = Field(min_length=8)


def _request_id(request: Request) -> str:
    incoming = request.headers.get("x-request-id")
    if incoming and REQUEST_ID_PATTERN.fullmatch(incoming):
        return incoming
    return secrets.token_hex(12)


def _problem(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    problem_type: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", _request_id(request))
    payload = ProblemDetail(
        type=problem_type,
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status,
        content=payload.model_dump(mode="json"),
        media_type="application/problem+json",
        headers={"x-request-id": request_id},
    )


def create_app(
    repository_root: str | Path | None = None,
    *,
    store: ArtifactStore | None = None,
    verify_sources: bool = True,
) -> FastAPI:
    """Create a deterministic read-only API over one repository snapshot."""

    if store is not None and repository_root is not None:
        raise ValueError("pass either repository_root or store, not both")
    catalog = store or ArtifactStore(repository_root or Path.cwd(), verify_sources=verify_sources)
    web_root = Path(__file__).resolve().parents[1] / "web"
    if not (web_root / "index.html").is_file():
        raise ProductCatalogError(f"packaged web explorer is missing: {web_root}")

    app = FastAPI(
        title="CivicDecision OS API",
        summary="Evidence-typed urban decision artifacts",
        description=(
            "Read-only projections of versioned public sources, city bundles, scenario screens, "
            "evidence-gated DecisionPacks, and analytical benchmarks. The API preserves negative "
            "releases and never upgrades the claims in an underlying artifact."
        ),
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        contact={"name": "CivicDecision OS"},
        license_info={"name": "MIT", "identifier": "MIT"},
    )
    app.state.store = catalog
    app.add_middleware(GZipMiddleware, minimum_size=1_024, compresslevel=6)

    @app.middleware("http")
    async def product_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.request_id = _request_id(request)
        is_api_get = request.method == "GET" and request.url.path.startswith("/api/")
        response = await call_next(request)
        if (
            is_api_get
            and response.status_code == 200
            and request.headers.get("if-none-match") == catalog.etag
        ):
            response = Response(status_code=304)
        response.headers["x-request-id"] = request.state.request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["cross-origin-opener-policy"] = "same-origin"
        response.headers["cross-origin-resource-policy"] = "same-origin"
        response.headers["content-security-policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'none'"
        )
        if is_api_get and response.status_code in {200, 304}:
            response.headers["etag"] = catalog.etag
            response.headers["cache-control"] = "public, max-age=60, must-revalidate"
        elif request.url.path.startswith("/assets/") and response.status_code == 200:
            response.headers["cache-control"] = "public, max-age=3600"
        else:
            response.headers["cache-control"] = "no-store"
        return response

    @app.exception_handler(ProductNotFoundError)
    async def not_found(request: Request, exc: ProductNotFoundError) -> JSONResponse:
        return _problem(
            request,
            status=404,
            title="Artifact not found",
            detail=str(exc),
            problem_type="https://civicdecision.dev/problems/not-found",
        )

    @app.exception_handler(IntegrityError)
    @app.exception_handler(ProductCatalogError)
    async def catalog_failure(request: Request, exc: Exception) -> JSONResponse:
        return _problem(
            request,
            status=503,
            title="Catalog integrity failure",
            detail=str(exc),
            problem_type="https://civicdecision.dev/problems/catalog-integrity",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_failure(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(
            request,
            status=422,
            title="Request validation failed",
            detail=str(exc),
            problem_type="https://civicdecision.dev/problems/request-validation",
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_failure(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code
        title = {
            404: "Route not found",
            405: "Method not allowed",
        }.get(status, "HTTP request failed")
        return _problem(
            request,
            status=status,
            title=title,
            detail=str(exc.detail),
            problem_type=f"https://civicdecision.dev/problems/http-{status}",
        )

    @app.get("/healthz", response_model=ProductHealth, tags=["operations"])
    def health() -> ProductHealth:
        return ProductHealth(
            status="ok",
            version=__version__,
            catalog_fingerprint=catalog.catalog_fingerprint,
            checked_at=datetime.now(UTC),
        )

    @app.get("/readyz", response_model=ProductHealth, tags=["operations"])
    def readiness() -> ProductHealth:
        return health()

    @app.get("/api/v1/meta", response_model=CatalogSummary, tags=["catalog"])
    def meta() -> CatalogSummary:
        return catalog.summary

    @app.get("/api/v1/cities", response_model=CityPage, tags=["cities"])
    def cities(
        tier: Annotated[ProductTier | None, Query()] = None,
        q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        country_code: Annotated[
            str | None, Query(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
        ] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> CityPage:
        return catalog.list_cities(
            tier=tier,
            query=q,
            country_code=country_code,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/v1/cities/{city_id}", response_model=CityDetail, tags=["cities"])
    def city(
        city_id: Annotated[
            str,
            PathParameter(min_length=1, max_length=160, pattern=IDENTIFIER_PATTERN),
        ],
    ) -> CityDetail:
        return catalog.city_detail(city_id)

    @app.get("/api/v1/scenarios", response_model=ScenarioPage, tags=["scenarios"])
    def scenarios(
        kind: Annotated[ScenarioKind | None, Query()] = None,
        city_id: Annotated[str | None, Query(max_length=120)] = None,
        suite: Annotated[str | None, Query(max_length=100)] = None,
        status: Annotated[ScenarioStatus | None, Query()] = None,
        q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ScenarioPage:
        return catalog.list_scenarios(
            kind=kind,
            city_id=city_id,
            suite=suite,
            status=status,
            query=q,
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/api/v1/scenarios/{execution_id}",
        response_model=ScenarioDetail,
        tags=["scenarios"],
    )
    def scenario(
        execution_id: Annotated[
            str,
            PathParameter(min_length=1, max_length=160, pattern=IDENTIFIER_PATTERN),
        ],
    ) -> ScenarioDetail:
        return catalog.scenario_detail(execution_id)

    @app.get(
        "/api/v1/decision-packs",
        response_model=ScenarioPage,
        tags=["decision-packs"],
    )
    def decision_packs(
        city_id: Annotated[str | None, Query(max_length=120)] = None,
        status: Annotated[ScenarioStatus | None, Query()] = None,
        q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> ScenarioPage:
        return catalog.list_decision_packs(
            city_id=city_id,
            status=status,
            query=q,
            limit=limit,
            offset=offset,
        )

    @app.get(
        "/api/v1/decision-packs/{execution_id}",
        response_model=DecisionPack,
        tags=["decision-packs"],
    )
    def decision_pack(
        execution_id: Annotated[
            str,
            PathParameter(min_length=1, max_length=160, pattern=IDENTIFIER_PATTERN),
        ],
    ) -> DecisionPack:
        return catalog.decision_pack(execution_id)

    @app.get(
        "/api/v1/decision-packs/{execution_id}/brief",
        response_class=PlainTextResponse,
        tags=["decision-packs"],
    )
    def decision_brief(
        execution_id: Annotated[
            str,
            PathParameter(min_length=1, max_length=160, pattern=IDENTIFIER_PATTERN),
        ],
        format: Annotated[Literal["markdown"], Query()] = "markdown",
    ) -> PlainTextResponse:
        del format
        return PlainTextResponse(
            catalog.decision_brief(execution_id),
            media_type="text/markdown; charset=utf-8",
            headers={"content-disposition": f'inline; filename="{execution_id}-decision-brief.md"'},
        )

    @app.get("/api/v1/sources", response_model=SourcePage, tags=["sources"])
    def sources(
        source_id: Annotated[str | None, Query(max_length=120)] = None,
        publisher: Annotated[str | None, Query(max_length=120)] = None,
        q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> SourcePage:
        return catalog.list_sources(
            source_id=source_id,
            publisher=publisher,
            query=q,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/v1/suites", response_model=list[SuiteOverview], tags=["catalog"])
    def suites() -> list[SuiteOverview]:
        return catalog.suites()

    @app.get("/api/v1/benchmarks", response_model=BenchmarkOverview, tags=["benchmarks"])
    def benchmarks() -> BenchmarkOverview:
        return catalog.benchmark_overview()

    @app.get(
        "/api/v1/evidence/deep",
        response_model=TierDEvidenceSummary,
        tags=["evidence"],
    )
    def deep_evidence() -> TierDEvidenceSummary:
        return catalog.deep_evidence

    app.mount("/assets", StaticFiles(directory=web_root / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def explorer() -> FileResponse:
        return FileResponse(web_root / "index.html", media_type="text/html")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(web_root / "favicon.svg", media_type="image/svg+xml")

    return app


__all__ = ["ProblemDetail", "create_app"]
