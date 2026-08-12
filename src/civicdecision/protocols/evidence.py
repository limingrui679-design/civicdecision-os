"""Evidence type system and release gates."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from civicdecision.protocols.base import IdentifiedModel


class EvidenceType(StrEnum):
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    CAUSAL = "causal"
    SIMULATED = "simulated"
    OPTIMIZED = "optimized"
    PROPOSED = "proposed"


class EvidenceStatus(StrEnum):
    ESTABLISHED = "established"
    LIMITED = "limited"
    FAILED = "failed"
    INSUFFICIENT = "insufficient_evidence"


class EvidenceItem(IdentifiedModel):
    """A typed analytical statement with evidence-specific requirements."""

    type: EvidenceType
    status: EvidenceStatus
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    method: str | None = None
    identification_strategy: str | None = None
    diagnostics: list[str] = Field(default_factory=list)
    scenario_ref: str | None = None
    objective: str | None = None
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_gate(self) -> EvidenceItem:
        if self.type is EvidenceType.OBSERVED and not self.source_refs:
            raise ValueError("observed evidence requires at least one source reference")
        if self.type is EvidenceType.ESTIMATED and not self.method:
            raise ValueError("estimated evidence requires a method")
        if self.type is EvidenceType.CAUSAL:
            if not self.identification_strategy:
                raise ValueError("causal evidence requires an identification strategy")
            if not self.diagnostics:
                raise ValueError("causal evidence requires diagnostics or refutations")
        if self.type is EvidenceType.SIMULATED and not self.scenario_ref:
            raise ValueError("simulated evidence requires a scenario reference")
        if self.type is EvidenceType.OPTIMIZED:
            if not self.objective:
                raise ValueError("optimized evidence requires an objective")
            if not self.constraints:
                raise ValueError("optimized evidence requires named constraints")
        if self.type is EvidenceType.PROPOSED and not self.limitations:
            raise ValueError("proposed evidence requires explicit limitations")
        if (
            self.status in {EvidenceStatus.FAILED, EvidenceStatus.INSUFFICIENT}
            and not self.limitations
        ):
            raise ValueError("failed or insufficient evidence must explain limitations")
        return self
