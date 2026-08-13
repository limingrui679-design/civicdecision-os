"""Tier-D city contracts, source specifications, compiler, and verifier."""

from civicdecision.deep.build import (
    TierDBuildArtifacts,
    TierDCompilation,
    build_tier_d_artifacts,
    compile_tier_d_reference,
    write_tier_d_artifacts,
)
from civicdecision.deep.compile import compile_deep_scenario
from civicdecision.deep.fetch import fetch_tier_d_context, fetch_tier_d_sources
from civicdecision.deep.models import (
    DeepCityBundle,
    DeepScenarioPack,
    TierDEvidenceSummary,
    TierDRegistry,
)
from civicdecision.deep.templates import DEEP_SCENARIO_TEMPLATES

__all__ = [
    "DEEP_SCENARIO_TEMPLATES",
    "DeepCityBundle",
    "DeepScenarioPack",
    "TierDBuildArtifacts",
    "TierDCompilation",
    "TierDEvidenceSummary",
    "TierDRegistry",
    "build_tier_d_artifacts",
    "compile_deep_scenario",
    "compile_tier_d_reference",
    "fetch_tier_d_context",
    "fetch_tier_d_sources",
    "write_tier_d_artifacts",
]
