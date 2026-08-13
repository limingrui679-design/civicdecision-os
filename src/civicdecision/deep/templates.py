"""Twelve non-duplicative deep-city scenario designs and their claim boundaries."""

from __future__ import annotations

from civicdecision.deep.models import (
    ApplicationSuite,
    DeepScenarioTemplate,
    ScenarioCompletionStrategy,
    SourceRole,
)
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.scenario import AnalysisMode

ANALYTICAL_MODES = [
    AnalysisMode.FORECAST,
    AnalysisMode.SIMULATION,
    AnalysisMode.OPTIMIZATION,
]
ANALYTICAL_EVIDENCE = [
    EvidenceType.OBSERVED,
    EvidenceType.ESTIMATED,
    EvidenceType.SIMULATED,
    EvidenceType.OPTIMIZED,
    EvidenceType.PROPOSED,
]
COMMON_PROHIBITED = [
    "Do not call service requests verified incidents, harms, needs, or completed outcomes.",
    "Do not describe proposed action coefficients as observed or causal effects.",
    "Do not present a planning-support option as a municipal recommendation or deployment.",
]
COMMON_ASSUMPTIONS = [
    "The bounded 2025 reference window is treated as an operational workload sample.",
    "Scenario action effects, costs, capacities, and risks are declared planning assumptions.",
]
COMMON_LIMITATIONS = [
    "Reporting behavior, publication coverage, taxonomy, and workflow differ across cities.",
    "A transparent baseline can support planning exercises but cannot validate intervention "
    "impact.",
]


def _analytical(
    *,
    order: int,
    identifier: str,
    suite: ApplicationSuite,
    title: str,
    question: str,
    strategy: ScenarioCompletionStrategy,
    roles: list[SourceRole],
    intended_claim: str,
    keywords: list[str] | None = None,
) -> DeepScenarioTemplate:
    normalized_keywords = sorted(keywords or [])
    return DeepScenarioTemplate(
        template_order=order,
        template_id=identifier,
        suite=suite,
        title=title,
        question=question,
        completion_strategy=strategy,
        category_keywords=normalized_keywords,
        minimum_matching_requests=100 if normalized_keywords else 0,
        required_source_roles=roles,
        analysis_modes=ANALYTICAL_MODES,
        evidence_requirements=ANALYTICAL_EVIDENCE,
        intended_claim=intended_claim,
        prohibited_claims=COMMON_PROHIBITED,
        assumptions=COMMON_ASSUMPTIONS,
        limitations=COMMON_LIMITATIONS,
    )


DEEP_SCENARIO_TEMPLATES = (
    _analytical(
        order=1,
        identifier="deep.public-service.total-demand.v1",
        suite=ApplicationSuite.PUBLIC_SERVICE,
        title="Citywide service-request workload baseline",
        question=(
            "What bounded planning portfolio remains attractive under forecast and action-effect "
            "uncertainty for the observed public service-request workload?"
        ),
        strategy=ScenarioCompletionStrategy.TOTAL_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND],
        intended_claim=(
            "A reproducible planning comparison conditioned on observed aggregate request counts "
            "and explicit hypothetical action parameters."
        ),
    ),
    _analytical(
        order=2,
        identifier="deep.public-service.seasonal-staffing.v1",
        suite=ApplicationSuite.PUBLIC_SERVICE,
        title="Seasonal service-capacity planning",
        question=(
            "How does a bounded service-capacity portfolio compare when recent daily request "
            "seasonality and implementation uncertainty are retained?"
        ),
        strategy=ScenarioCompletionStrategy.TOTAL_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND],
        intended_claim=(
            "A seasonal workload planning exercise, not a forecast of staffing productivity or "
            "a personnel prescription."
        ),
    ),
    _analytical(
        order=3,
        identifier="deep.public-service.sanitation-workload.v1",
        suite=ApplicationSuite.PUBLIC_SERVICE,
        title="Sanitation-related request workload planning",
        question=(
            "What planning portfolio is robust for public request categories whose labels match "
            "a declared sanitation keyword rule?"
        ),
        strategy=ScenarioCompletionStrategy.CATEGORY_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND],
        intended_claim=(
            "A taxonomy-explicit workload subset and simulated planning comparison; category "
            "matching does not verify sanitation conditions."
        ),
        keywords=["clean", "dumping", "garbage", "litter", "recycling", "trash", "waste"],
    ),
    _analytical(
        order=4,
        identifier="deep.climate.heat-service-surge.v1",
        suite=ApplicationSuite.CLIMATE_DISASTER,
        title="Heat-context service continuity",
        question=(
            "How should a hypothetical continuity portfolio be stress-tested alongside the "
            "observed request series and a gridded heat context?"
        ),
        strategy=ScenarioCompletionStrategy.TOTAL_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.CLIMATE_CONTEXT],
        intended_claim=(
            "A compound planning stress test that juxtaposes, but does not causally link, request "
            "workload and gridded heat."
        ),
    ),
    _analytical(
        order=5,
        identifier="deep.climate.rainfall-continuity.v1",
        suite=ApplicationSuite.CLIMATE_DISASTER,
        title="Rainfall-context service continuity",
        question=(
            "Which bounded continuity option remains preferable under workload and hypothetical "
            "rainfall-response uncertainty?"
        ),
        strategy=ScenarioCompletionStrategy.TOTAL_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.CLIMATE_CONTEXT],
        intended_claim=(
            "A rainfall-context planning exercise without claiming that precipitation caused the "
            "observed requests."
        ),
    ),
    _analytical(
        order=6,
        identifier="deep.housing.request-triage.v1",
        suite=ApplicationSuite.HOUSING_LAND_USE,
        title="Housing-related request triage",
        question=(
            "What bounded triage portfolio is supported for request labels matching a declared "
            "housing and building rule?"
        ),
        strategy=ScenarioCompletionStrategy.CATEGORY_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.DEMOGRAPHIC_CONTEXT],
        intended_claim=(
            "A request-taxonomy planning subset, not a measure of housing quality, violations, "
            "tenure outcomes, or regeneration impact."
        ),
        keywords=[
            "apartment",
            "building",
            "heat",
            "housing",
            "landlord",
            "residential",
            "vacant",
        ],
    ),
    _analytical(
        order=7,
        identifier="deep.health.environmental-request-screen.v1",
        suite=ApplicationSuite.POPULATION_HEALTH,
        title="Environmental request workload screen",
        question=(
            "How does a bounded planning portfolio compare for request labels matching a declared "
            "environmental-context rule?"
        ),
        strategy=ScenarioCompletionStrategy.CATEGORY_DEMAND,
        roles=[
            SourceRole.MUNICIPAL_DEMAND,
            SourceRole.CLIMATE_CONTEXT,
            SourceRole.DEMOGRAPHIC_CONTEXT,
        ],
        intended_claim=(
            "An environmental request-label screen with population and climate context, not an "
            "exposure, diagnosis, health-risk, or causal-effect estimate."
        ),
        keywords=[
            "air",
            "environment",
            "illegal dumping",
            "noise",
            "pest",
            "tree",
            "waste",
            "water",
        ],
    ),
    _analytical(
        order=8,
        identifier="deep.infrastructure.maintenance-portfolio.v1",
        suite=ApplicationSuite.INFRASTRUCTURE_FINANCE,
        title="Infrastructure-maintenance request portfolio",
        question=(
            "What bounded portfolio is robust for request labels matching a declared public-asset "
            "maintenance rule?"
        ),
        strategy=ScenarioCompletionStrategy.CATEGORY_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.CLIMATE_CONTEXT],
        intended_claim=(
            "A request-based maintenance planning proxy, not an asset-condition survey, capital "
            "budget, engineering design, or financial return."
        ),
        keywords=[
            "bridge",
            "light",
            "pothole",
            "road",
            "sewer",
            "sidewalk",
            "signal",
            "street",
            "water",
        ],
    ),
    _analytical(
        order=9,
        identifier="deep.equity.area-balance.v1",
        suite=ApplicationSuite.BEHAVIORAL_EQUITY,
        title="Area-level request balance",
        question=(
            "How does an area-balance constraint change a bounded service planning portfolio when "
            "only aggregate operational areas are available?"
        ),
        strategy=ScenarioCompletionStrategy.TOTAL_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.DEMOGRAPHIC_CONTEXT],
        intended_claim=(
            "A distributional planning diagnostic over operational area labels, not a demographic "
            "equity finding or individual behavioral inference."
        ),
    ),
    _analytical(
        order=10,
        identifier="deep.mobility.accessibility-request.v1",
        suite=ApplicationSuite.MOBILITY_ACCESS,
        title="Accessibility-related request planning",
        question=(
            "What bounded portfolio is supported for request labels matching a declared physical-"
            "accessibility rule without a routable network?"
        ),
        strategy=ScenarioCompletionStrategy.CATEGORY_DEMAND,
        roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.GEOGRAPHIC_IDENTITY],
        intended_claim=(
            "A request-label workload plan only; it does not measure route accessibility, travel "
            "time, disability experience, or compliance."
        ),
        keywords=["accessib", "ada", "curb", "sidewalk", "wheelchair"],
    ),
    DeepScenarioTemplate(
        template_order=11,
        template_id="deep.equity.causal-service-effectiveness.v1",
        suite=ApplicationSuite.BEHAVIORAL_EQUITY,
        title="Causal service-effectiveness gate",
        question=(
            "Can the public aggregate snapshots identify a causal effect of a service intervention "
            "on area-level outcomes?"
        ),
        completion_strategy=ScenarioCompletionStrategy.REQUIRED_CAUSAL_DESIGN,
        category_keywords=[],
        minimum_matching_requests=0,
        required_source_roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.DEMOGRAPHIC_CONTEXT],
        analysis_modes=[AnalysisMode.DESCRIPTIVE, AnalysisMode.CAUSAL],
        evidence_requirements=[EvidenceType.OBSERVED, EvidenceType.CAUSAL],
        intended_claim=(
            "An explicit insufficient-evidence release unless a dated intervention, comparison "
            "group, outcome panel, and identification diagnostics exist."
        ),
        prohibited_claims=[
            "Do not infer treatment effects from before/after request counts.",
            "Do not use request status as verified service resolution or welfare impact.",
        ],
        assumptions=[
            "No intervention assignment, treated cohort, or counterfactual design is present in "
            "the committed aggregate source layer."
        ],
        limitations=[
            "A causal question is retained as a negative evidence-gate test, not silently reduced "
            "to an associational claim."
        ],
    ),
    DeepScenarioTemplate(
        template_order=12,
        template_id="deep.mobility.real-time-reroute.v1",
        suite=ApplicationSuite.MOBILITY_ACCESS,
        title="Real-time multimodal rerouting gate",
        question=(
            "Can the committed city evidence support real-time multimodal rerouting and disruption "
            "allocation?"
        ),
        completion_strategy=ScenarioCompletionStrategy.REQUIRED_NETWORK,
        category_keywords=[],
        minimum_matching_requests=0,
        required_source_roles=[SourceRole.MUNICIPAL_DEMAND, SourceRole.NETWORK],
        analysis_modes=[AnalysisMode.DESCRIPTIVE, AnalysisMode.OPTIMIZATION],
        evidence_requirements=[EvidenceType.OBSERVED, EvidenceType.PROPOSED],
        intended_claim=(
            "An explicit insufficient-evidence release until versioned routable networks, service "
            "calendars, disruptions, and impedance validation are bound."
        ),
        prohibited_claims=[
            "Do not treat city polygons or request-area labels as a routable transport network.",
            "Do not call a proposed allocation a real-time routing result.",
        ],
        assumptions=[
            "No GTFS, pedestrian graph, road topology, live vehicle state, or disruption feed is "
            "included in this milestone."
        ],
        limitations=[
            "The negative release demonstrates a missing-network gate and does not evaluate actual "
            "mobility performance."
        ],
    ),
)


if [item.template_order for item in DEEP_SCENARIO_TEMPLATES] != list(range(1, 13)):
    raise RuntimeError("deep scenario template order must be contiguous")
if len({item.template_id for item in DEEP_SCENARIO_TEMPLATES}) != 12:
    raise RuntimeError("deep scenario template identifiers must be unique")


__all__ = ["DEEP_SCENARIO_TEMPLATES"]
