from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from civicdecision.analysis import forecasting
from civicdecision.analysis.forecasting import (
    ForecastCandidate,
    ForecastConfig,
    ForecastMethod,
    ForecastRun,
    ForecastStatus,
    TimeSeriesPoint,
    run_baseline_forecast,
)
from civicdecision.errors import AnalysisError
from civicdecision.protocols.evidence import EvidenceType

START = datetime(2024, 1, 1, tzinfo=UTC)
CREATED = datetime(2025, 1, 1, tzinfo=UTC)


def series(values: list[float], *, step_days: int = 1) -> list[TimeSeriesPoint]:
    return [
        TimeSeriesPoint(timestamp=START + timedelta(days=index * step_days), value=value)
        for index, value in enumerate(values)
    ]


def seasonal_run() -> ForecastRun:
    values = [float(10 + index) for _ in range(10) for index in range(7)]
    return run_baseline_forecast(
        run_id="forecast.seasonal.qualification",
        series_id="synthetic.weekly-pattern",
        points=series(values),
        source_refs=["synthetic-fixture.weekly-pattern"],
        config=ForecastConfig(
            horizon=7,
            backtest_folds=6,
            minimum_backtest_folds=3,
            minimum_train_size=14,
            moving_average_window=7,
            seasonal_period=7,
        ),
        created_at=CREATED,
    )


def test_seasonal_baseline_wins_exact_pattern_with_zero_error() -> None:
    run = seasonal_run()
    assert run.status is ForecastStatus.COMPLETED
    assert run.selected_method is ForecastMethod.SEASONAL_NAIVE
    assert [item.point for item in run.forecast] == [float(10 + index) for index in range(7)]
    winner = next(item for item in run.candidates if item.method is run.selected_method)
    assert winner.metrics is not None
    assert winner.metrics.mae == 0
    assert winner.conformal_radius == 0
    assert all(item.lower == item.point == item.upper for item in run.forecast)
    assert run.evidence_type is EvidenceType.ESTIMATED


def test_forecast_run_is_hash_deterministic_and_keeps_fold_predictions() -> None:
    first = seasonal_run()
    second = seasonal_run()
    assert first.content_hash() == second.content_hash()
    assert all(candidate.folds for candidate in first.candidates if candidate.eligible)
    assert all(
        fold.origin_timestamp < fold.target_timestamps[0]
        for candidate in first.candidates
        for fold in candidate.folds
    )


def test_drift_wins_deterministic_linear_trend() -> None:
    run = run_baseline_forecast(
        run_id="forecast.trend.qualification",
        series_id="synthetic.linear-trend",
        points=series([float(index) for index in range(50)]),
        source_refs=["synthetic-fixture.linear-trend"],
        config=ForecastConfig(
            horizon=3,
            backtest_folds=8,
            minimum_train_size=10,
            moving_average_window=5,
            seasonal_period=7,
        ),
        created_at=CREATED,
    )
    assert run.selected_method is ForecastMethod.DRIFT
    assert [item.point for item in run.forecast] == [50, 51, 52]


def test_nonnegative_gate_clamps_predictions_and_interval_floor() -> None:
    run = run_baseline_forecast(
        run_id="forecast.nonnegative.qualification",
        series_id="synthetic.decline",
        points=series([float(20 - index) for index in range(20)]),
        source_refs=["synthetic-fixture.decline"],
        config=ForecastConfig(
            horizon=3,
            backtest_folds=4,
            minimum_train_size=5,
            moving_average_window=3,
            seasonal_period=3,
            require_nonnegative=True,
        ),
        created_at=CREATED,
    )
    assert all(item.point >= 0 and item.lower >= 0 for item in run.forecast)


def test_short_regular_series_releases_insufficient_evidence() -> None:
    run = run_baseline_forecast(
        run_id="forecast.short.qualification",
        series_id="synthetic.short",
        points=series([1.0]),
        source_refs=["synthetic-fixture.short"],
        config=ForecastConfig(minimum_train_size=2),
        created_at=CREATED,
    )
    assert run.status is ForecastStatus.INSUFFICIENT_EVIDENCE
    assert run.failure_reason
    assert run.selected_method is None
    assert not run.forecast


def test_candidate_specific_history_gate_does_not_block_eligible_baselines() -> None:
    run = run_baseline_forecast(
        run_id="forecast.partial-candidates.qualification",
        series_id="synthetic.partial-candidates",
        points=series([float(index % 3) for index in range(16)]),
        source_refs=["synthetic-fixture.partial-candidates"],
        config=ForecastConfig(
            horizon=2,
            backtest_folds=4,
            minimum_backtest_folds=2,
            minimum_train_size=4,
            moving_average_window=3,
            seasonal_period=30,
        ),
        created_at=CREATED,
    )
    assert run.status is ForecastStatus.COMPLETED
    seasonal = next(item for item in run.candidates if item.method is ForecastMethod.SEASONAL_NAIVE)
    assert not seasonal.eligible
    assert seasonal.exclusion_reason


@pytest.mark.parametrize(
    ("points", "message"),
    [
        ([], "at least one observation"),
        (list(reversed(series([1, 2, 3]))), "sorted"),
        (
            [
                TimeSeriesPoint(timestamp=START, value=1),
                TimeSeriesPoint(timestamp=START, value=2),
            ],
            "unique",
        ),
        (
            [
                TimeSeriesPoint(timestamp=START, value=1),
                TimeSeriesPoint(timestamp=START + timedelta(days=1), value=2),
                TimeSeriesPoint(timestamp=START + timedelta(days=3), value=3),
            ],
            "regular interval",
        ),
    ],
)
def test_forecast_input_sequence_guards(points: list[TimeSeriesPoint], message: str) -> None:
    with pytest.raises(AnalysisError, match=message):
        run_baseline_forecast(
            run_id="forecast.invalid",
            series_id="synthetic.invalid",
            points=points,
            source_refs=["synthetic-fixture.invalid"],
            created_at=CREATED,
        )


def test_time_series_point_rejects_naive_timestamp_and_nonfinite_value() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        TimeSeriesPoint(timestamp=datetime(2024, 1, 1), value=1)
    with pytest.raises(ValidationError, match="finite"):
        TimeSeriesPoint(timestamp=START, value=float("nan"))


def test_forecast_config_rejects_duplicate_methods_and_inverted_fold_counts() -> None:
    with pytest.raises(ValidationError, match="methods must be unique"):
        ForecastConfig(methods=[ForecastMethod.NAIVE, ForecastMethod.NAIVE])
    with pytest.raises(ValidationError, match="cannot exceed"):
        ForecastConfig(backtest_folds=2, minimum_backtest_folds=3)


def test_low_level_forecast_math_guards() -> None:
    config = ForecastConfig(minimum_train_size=2, moving_average_window=3)
    with pytest.raises(AnalysisError, match="cannot be empty"):
        forecasting._predict(ForecastMethod.NAIVE, [], 1, config)
    with pytest.raises(AnalysisError, match="requires two"):
        forecasting._predict(ForecastMethod.DRIFT, [1], 1, config)
    with pytest.raises(AnalysisError, match="shorter than its window"):
        forecasting._predict(ForecastMethod.MOVING_AVERAGE, [1, 2], 1, config)
    with pytest.raises(AnalysisError, match="shorter than its period"):
        forecasting._predict(ForecastMethod.SEASONAL_NAIVE, [1, 2], 1, config)
    with pytest.raises(AnalysisError, match="requires errors"):
        forecasting._conformal_radius([], 0.9)
    with pytest.raises(AnalysisError, match="aligned"):
        forecasting._metrics([1], [], 1)


def test_zero_actual_backtest_uses_mae_when_wape_is_undefined() -> None:
    metrics = forecasting._metrics([0, 0], [0, 1], 1)
    assert metrics.wape is None
    assert metrics.mae == 0.5


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update(evidence_type="simulated"),
            "estimated evidence",
        ),
        (
            lambda payload: payload.update(source_refs=["a", "a"]),
            "source references must be unique",
        ),
        (
            lambda payload: payload.update(selected_method=None),
            "require a winner",
        ),
        (
            lambda payload: payload["candidates"].append(payload["candidates"][0]),
            "candidate methods must be unique",
        ),
        (
            lambda payload: payload.update(failure_reason="not allowed"),
            "cannot have a failure reason",
        ),
    ],
)
def test_forecast_run_contract_rejects_claim_and_cross_object_drift(
    mutation: object, message: str
) -> None:
    payload = seasonal_run().model_dump(mode="json")
    mutation(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        ForecastRun.model_validate(payload)


def test_candidate_and_fold_contracts_reject_inconsistent_state() -> None:
    payload = seasonal_run().candidates[0].model_dump(mode="json")
    payload["eligible"] = False
    with pytest.raises(ValidationError, match="exclusion reason"):
        ForecastCandidate.model_validate(payload)

    fold = seasonal_run().candidates[0].folds[0].model_dump(mode="json")
    fold["predicted"].pop()
    with pytest.raises(ValidationError, match="vectors must align"):
        forecasting.ForecastFold.model_validate(fold)


def test_insufficient_run_rejects_output_and_missing_reason() -> None:
    run = run_baseline_forecast(
        run_id="forecast.short.contract",
        series_id="synthetic.short-contract",
        points=series([1.0]),
        source_refs=["synthetic-fixture.short-contract"],
        created_at=CREATED,
    )
    payload = run.model_dump(mode="json")
    payload["failure_reason"] = None
    with pytest.raises(ValidationError, match="require a failure reason"):
        ForecastRun.model_validate(payload)
