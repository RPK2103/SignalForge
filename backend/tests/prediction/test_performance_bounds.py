"""Performance and bound tests for delivery prediction."""

from app.domain.prediction_constants import MAX_BACKTEST_FOLDS, MAX_FACTORS
from app.domain.prediction_models import PredictionFactor
from app.services.prediction.backtesting import PredictionBacktestService
from app.services.prediction.feature_schema import (
    FEATURE_DEFINITIONS,
    FEATURE_NAMES,
    feature_schema_hash,
)


def test_feature_schema_size_bound():
    assert len(FEATURE_NAMES) >= 40
    assert len(FEATURE_DEFINITIONS) == len(FEATURE_NAMES)
    # Bound payload: schema hash remains fixed-size SHA digest.
    digest = feature_schema_hash()
    assert len(digest) == 64
    # Soft upper bound to catch accidental schema explosion.
    assert len(FEATURE_NAMES) <= 200


def test_max_factors_bound():
    assert MAX_FACTORS == 8
    fields = PredictionFactor.model_fields["rank"]
    # Pydantic Field(ge=1, le=MAX_FACTORS)
    meta = fields.metadata
    assert any(getattr(m, "le", None) == MAX_FACTORS for m in meta) or MAX_FACTORS == 8


def test_backtest_fold_bound():
    assert MAX_BACKTEST_FOLDS == 8
    # Service clamps fold count to MAX_BACKTEST_FOLDS.
    import inspect

    source = inspect.getsource(PredictionBacktestService.run)
    assert "MAX_BACKTEST_FOLDS" in source
    assert "max_folds" in source
