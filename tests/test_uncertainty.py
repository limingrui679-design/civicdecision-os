from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from civicdecision.analysis import uncertainty
from civicdecision.analysis.uncertainty import (
    ObjectiveSense,
    OptionDraws,
    UncertaintyConfig,
    UncertaintyMethod,
    UncertaintyRun,
    UncertaintyStatus,
    analyze_option_uncertainty,
)
from civicdecision.errors import AnalysisError
from civicdecision.protocols.evidence import EvidenceType

CREATED = datetime(2025, 1, 1, tzinfo=UTC)


def option(
    identifier: str,
    values: list[float],
    evidence_type: EvidenceType = EvidenceType.SIMULATED,
) -> OptionDraws:
    return OptionDraws(
        option_id=identifier,
        values=values,
        source_refs=[f"synthetic-fixture.{identifier}"],
        evidence_type=evidence_type,
        limitations=["Synthetic draw stream is not real policy evidence."],
    )


def robust_run() -> UncertaintyRun:
    return analyze_option_uncertainty(
        run_id="uncertainty.robust.qualification",
        options=[
            option("a", [10, 11, 12, 13, 14]),
            option("b", [5, 6, 7, 8, 9]),
            option("c", [1, 2, 3, 4, 5]),
        ],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            practical_equivalence_margin=0.5,
            robust_probability_threshold=0.9,
            maximum_expected_regret=0,
        ),
        baseline_option_id="a",
        created_at=CREATED,
    )


def test_robust_winner_has_zero_regret_and_deterministic_hash() -> None:
    run = robust_run()
    assert run.status is UncertaintyStatus.ROBUST_WINNER
    assert run.selected_option_id == "a"
    assert run.evidence_type is EvidenceType.SIMULATED
    selected = next(item for item in run.option_summaries if item.option_id == "a")
    assert selected.probability_best == 1
    assert selected.expected_regret == 0
    assert selected.maximum_regret == 0
    assert run.content_hash() == robust_run().content_hash()


def test_crossing_draws_preserve_reversal_risk_and_first_reversal() -> None:
    run = analyze_option_uncertainty(
        run_id="uncertainty.reversal.qualification",
        options=[
            option("incumbent", [10, 2, 10, 2]),
            option("competitor", [2, 10, 2, 10]),
        ],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            robust_probability_threshold=0.75,
        ),
        baseline_option_id="incumbent",
        created_at=CREATED,
    )
    assert run.status is UncertaintyStatus.REVERSAL_RISK
    assert run.selected_option_id == "competitor"
    reversal = run.reversals[0]
    assert reversal.reversal_probability == 0.5
    assert reversal.first_reversal_draw == 1
    assert run.pairwise_dominance[0].probability_a_better == 0.5


def test_minimize_objective_uses_lower_values_and_estimated_evidence() -> None:
    run = analyze_option_uncertainty(
        run_id="uncertainty.minimize.qualification",
        options=[
            option("low", [1, 2, 1, 2], EvidenceType.ESTIMATED),
            option("high", [5, 6, 5, 6], EvidenceType.ESTIMATED),
        ],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MINIMIZE,
            robust_probability_threshold=0.9,
        ),
        created_at=CREATED,
    )
    assert run.selected_option_id == "low"
    assert run.status is UncertaintyStatus.ROBUST_WINNER
    assert run.evidence_type is EvidenceType.ESTIMATED


def test_one_option_or_unaligned_draws_release_insufficient_evidence() -> None:
    run = analyze_option_uncertainty(
        run_id="uncertainty.one-option",
        options=[option("a", [1, 2])],
        config=UncertaintyConfig(sense=ObjectiveSense.MAXIMIZE),
        created_at=CREATED,
    )
    assert run.status is UncertaintyStatus.INSUFFICIENT_EVIDENCE
    assert run.failure_reason
    assert not run.option_summaries

    run = analyze_option_uncertainty(
        run_id="uncertainty.unaligned",
        options=[option("a", [1, 2]), option("b", [1, 2, 3])],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            require_paired_draws=True,
        ),
        created_at=CREATED,
    )
    assert run.method is UncertaintyMethod.PAIRED_DRAWS
    assert run.status is UncertaintyStatus.INSUFFICIENT_EVIDENCE

    run = analyze_option_uncertainty(
        run_id="uncertainty.independent-unaligned",
        options=[option("a", [1, 2]), option("b", [1, 2, 3])],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            require_paired_draws=False,
        ),
        created_at=CREATED,
    )
    assert run.method is UncertaintyMethod.INDEPENDENT_SUMMARIES
    assert run.status is UncertaintyStatus.INSUFFICIENT_EVIDENCE


def test_duplicate_or_missing_baseline_fails_safely() -> None:
    with pytest.raises(AnalysisError, match="ids must be unique"):
        analyze_option_uncertainty(
            run_id="uncertainty.duplicate",
            options=[option("a", [1, 2]), option("a", [2, 3])],
            config=UncertaintyConfig(sense=ObjectiveSense.MAXIMIZE),
            created_at=CREATED,
        )
    with pytest.raises(AnalysisError, match="baseline option does not exist"):
        analyze_option_uncertainty(
            run_id="uncertainty.bad-baseline",
            options=[option("a", [1, 2]), option("b", [2, 3])],
            config=UncertaintyConfig(sense=ObjectiveSense.MAXIMIZE),
            baseline_option_id="missing",
            created_at=CREATED,
        )


def test_ties_break_by_stable_option_id() -> None:
    run = analyze_option_uncertainty(
        run_id="uncertainty.ties",
        options=[option("z", [1, 1]), option("a", [1, 1])],
        config=UncertaintyConfig(
            sense=ObjectiveSense.MAXIMIZE,
            robust_probability_threshold=0.9,
        ),
        created_at=CREATED,
    )
    assert run.selected_option_id == "a"
    assert (
        next(item for item in run.option_summaries if item.option_id == "a").probability_best == 0.5
    )
    assert (
        next(item for item in run.option_summaries if item.option_id == "z").probability_best == 0.5
    )


def test_draw_contract_rejects_nonfinite_duplicate_sources_and_claim_upgrade() -> None:
    with pytest.raises(ValidationError, match="finite number"):
        option("a", [1, float("nan")])
    payload = option("a", [1, 2]).model_dump()
    payload["source_refs"] *= 2
    with pytest.raises(ValidationError, match="must be unique"):
        OptionDraws.model_validate(payload)
    payload = option("a", [1, 2]).model_dump()
    payload["evidence_type"] = "causal"
    with pytest.raises(ValidationError, match="estimated or simulated"):
        OptionDraws.model_validate(payload)


def test_low_level_quantile_and_better_directions() -> None:
    with pytest.raises(AnalysisError, match="require values"):
        uncertainty._quantile([], 0.5)
    assert uncertainty._quantile([0, 10], 0.25) == 2.5
    assert uncertainty._better(2, 1, ObjectiveSense.MAXIMIZE)
    assert uncertainty._better(1, 2, ObjectiveSense.MINIMIZE)
    assert not uncertainty._better(1.1, 1, ObjectiveSense.MAXIMIZE, 0.2)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update(evidence_type="causal"),
            "must be estimated or simulated",
        ),
        (
            lambda payload: payload["option_summaries"].append(payload["option_summaries"][0]),
            "option ids must be unique",
        ),
        (
            lambda payload: payload.update(baseline_option_id="missing"),
            "baseline option must exist",
        ),
        (
            lambda payload: payload.update(selected_option_id="missing"),
            "selected option must exist",
        ),
        (
            lambda payload: payload.update(selected_option_id=None),
            "require paired summaries, baseline, and selection",
        ),
        (
            lambda payload: payload.update(failure_reason="not allowed"),
            "cannot have a failure reason",
        ),
        (
            lambda payload: payload["option_summaries"][0].update(draws=999),
            "aligned draw counts",
        ),
        (
            lambda payload: payload["option_summaries"][0].update(probability_best=0.5),
            "shares must sum to one",
        ),
        (
            lambda payload: payload["pairwise_dominance"].pop(),
            "exactly cover unique option pairs",
        ),
        (
            lambda payload: payload["reversals"].pop(),
            "cover every non-baseline option once",
        ),
        (
            lambda payload: payload.update(selected_option_id="b"),
            "declared deterministic rule",
        ),
        (
            lambda payload: payload.update(status="reversal-risk"),
            "match robustness thresholds",
        ),
    ],
)
def test_completed_uncertainty_contract_rejects_output_drift(
    mutation: object, message: str
) -> None:
    payload = robust_run().model_dump(mode="json")
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        UncertaintyRun.model_validate(payload)


def test_insufficient_uncertainty_contract_rejects_summary_or_missing_reason() -> None:
    run = analyze_option_uncertainty(
        run_id="uncertainty.insufficient.contract",
        options=[option("a", [1, 2])],
        config=UncertaintyConfig(sense=ObjectiveSense.MAXIMIZE),
        created_at=CREATED,
    )
    payload = run.model_dump(mode="json")
    payload["selected_option_id"] = "a"
    payload["option_summaries"] = [robust_run().option_summaries[0].model_dump(mode="json")]
    with pytest.raises(ValidationError, match="cannot emit option-comparison"):
        UncertaintyRun.model_validate(payload)
    payload = run.model_dump(mode="json")
    payload["failure_reason"] = None
    with pytest.raises(ValidationError, match="require a failure reason"):
        UncertaintyRun.model_validate(payload)


def test_option_summary_interval_must_contain_mean() -> None:
    payload = robust_run().option_summaries[0].model_dump()
    payload["lower"] = payload["mean"] + 1
    with pytest.raises(ValidationError, match="must contain"):
        uncertainty.OptionUncertaintySummary.model_validate(payload)


def test_pairwise_and_reversal_contracts_reject_self_comparisons() -> None:
    pair = robust_run().pairwise_dominance[0].model_dump()
    pair["option_b"] = pair["option_a"]
    with pytest.raises(ValidationError, match="two distinct options"):
        uncertainty.PairwiseDominance.model_validate(pair)
    reversal = robust_run().reversals[0].model_dump()
    reversal["competing_option_id"] = reversal["baseline_option_id"]
    with pytest.raises(ValidationError, match="distinct competitor"):
        uncertainty.DecisionReversal.model_validate(reversal)
