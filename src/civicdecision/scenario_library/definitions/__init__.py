"""The seven-suite, 30-family scenario definition catalog."""

from civicdecision.scenario_library.definitions.behavioral_equity import BEHAVIORAL_FAMILIES
from civicdecision.scenario_library.definitions.climate import CLIMATE_FAMILIES
from civicdecision.scenario_library.definitions.health import HEALTH_FAMILIES
from civicdecision.scenario_library.definitions.housing import HOUSING_FAMILIES
from civicdecision.scenario_library.definitions.infrastructure import INFRASTRUCTURE_FAMILIES
from civicdecision.scenario_library.definitions.mobility import MOBILITY_FAMILIES
from civicdecision.scenario_library.definitions.public_service import PUBLIC_SERVICE_FAMILIES
from civicdecision.scenario_library.models import DecisionType
from civicdecision.scenario_library.seeds import FamilySeed

FAMILY_SEEDS: tuple[FamilySeed, ...] = (
    *CLIMATE_FAMILIES,
    *MOBILITY_FAMILIES,
    *HEALTH_FAMILIES,
    *HOUSING_FAMILIES,
    *PUBLIC_SERVICE_FAMILIES,
    *INFRASTRUCTURE_FAMILIES,
    *BEHAVIORAL_FAMILIES,
)


def _validate_definitions() -> None:
    if len(FAMILY_SEEDS) != 30:
        raise RuntimeError("scenario library must define exactly 30 families")
    if len({item.family_id for item in FAMILY_SEEDS}) != 30:
        raise RuntimeError("scenario family identifiers must be unique")
    for family in FAMILY_SEEDS:
        if len(family.designs) != 8:
            raise RuntimeError(f"scenario family must define eight designs: {family.family_id}")
        if {item.decision_type for item in family.designs} != set(DecisionType):
            raise RuntimeError(
                f"scenario family lacks the complete decision matrix: {family.family_id}"
            )
        if len({item.slug for item in family.designs}) != 8:
            raise RuntimeError(f"scenario design slugs must be unique within {family.family_id}")


_validate_definitions()

__all__ = ["FAMILY_SEEDS"]
