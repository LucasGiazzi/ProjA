"""Testes da divisão temporal, das features e das métricas, sem banco de dados."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from ml import dataset, evaluate, report, train


def dates_frame(days: pd.DatetimeIndex) -> pd.DataFrame:
    """Cria um conjunto mínimo com uma linha por dia."""
    return pd.DataFrame({dataset.DATE_COLUMN: days})


def test_split_keeps_a_gap_the_size_of_the_label_window() -> None:
    days = pd.date_range("2024-12-01", "2025-03-01")

    train_rows, test_rows = dataset.temporal_split(
        dates_frame(days), train_end=date(2024, 12, 31), label_window_days=30
    )

    assert train_rows[dataset.DATE_COLUMN].max() == pd.Timestamp("2024-12-31")
    assert test_rows[dataset.DATE_COLUMN].min() == pd.Timestamp("2025-01-31")


def test_split_never_mixes_periods() -> None:
    days = pd.date_range("2024-01-01", "2026-01-01")

    train_rows, test_rows = dataset.temporal_split(dates_frame(days))

    assert train_rows[dataset.DATE_COLUMN].max() < test_rows[dataset.DATE_COLUMN].min()


def test_label_and_identifiers_are_not_features() -> None:
    forbidden = {dataset.TARGET, "app_id", dataset.DATE_COLUMN}

    assert forbidden.isdisjoint(dataset.ALL_FEATURES)


def test_features_are_listed_once() -> None:
    assert len(dataset.ALL_FEATURES) == len(set(dataset.ALL_FEATURES))


def test_perfect_prediction_scores_perfectly() -> None:
    y_true = np.array([True, True, False, False])
    y_proba = np.array([0.9, 0.8, 0.2, 0.1])

    metrics = evaluate.classification_metrics(y_true, y_proba)

    assert metrics["accuracy"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["brier"] == pytest.approx(0.025)


def test_always_yes_has_full_recall_and_no_ranking() -> None:
    y_true = np.array([True, False, True, False])

    metrics = evaluate.classification_metrics(y_true, np.ones(4))

    assert metrics["recall"] == 1.0
    assert metrics["precision"] == 0.5
    assert metrics["roc_auc"] == 0.5


def test_calibration_compares_predicted_with_observed() -> None:
    y_true = np.array([True, False, True, True])
    y_proba = np.array([0.15, 0.15, 0.95, 0.95])

    table = evaluate.calibration_table(y_true, y_proba)

    assert table["rows"].tolist() == [2, 2]
    assert table["observed"].tolist() == [0.5, 1.0]


def test_calibrated_baseline_uses_training_rates_only() -> None:
    train_rows = pd.DataFrame(
        {
            dataset.BASELINE: [True, True, False, False],
            dataset.TARGET: [True, False, False, False],
        }
    )
    test_rows = pd.DataFrame({dataset.BASELINE: [True, False]})

    predictions = train.reference_predictions(train_rows, test_rows)

    assert predictions["Baseline sazonal calibrado"].tolist() == [0.5, 0.0]
    assert predictions["Baseline sazonal"].tolist() == [1.0, 0.0]


def test_lower_brier_counts_as_better() -> None:
    assert report.beats({"brier": 0.1}, {"brier": 0.2}, "brier")
    assert not report.beats({"f1": 0.1}, {"f1": 0.2}, "f1")
