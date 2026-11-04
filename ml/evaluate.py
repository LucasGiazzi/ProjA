"""Métricas de classificação e calibração."""

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

DECISION_THRESHOLD = 0.5
CALIBRATION_BINS = 10


def classification_metrics(y_true: np.ndarray, y_proba: np.ndarray) -> dict[str, float]:
    """Calcula as métricas do design, mais acurácia e AUC."""
    y_pred = y_proba >= DECISION_THRESHOLD
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "brier": brier_score_loss(y_true, y_proba),
        "roc_auc": roc_auc_score(y_true, y_proba),
    }


def calibration_table(y_true: np.ndarray, y_proba: np.ndarray) -> pd.DataFrame:
    """Compara, por faixa de probabilidade, o previsto com o observado."""
    bins = np.linspace(0, 1, CALIBRATION_BINS + 1)
    frame = pd.DataFrame({"y_true": y_true.astype(float), "y_proba": y_proba})
    frame["bin"] = pd.cut(frame["y_proba"], bins, include_lowest=True)
    table = frame.groupby("bin", observed=True).agg(
        rows=("y_true", "size"),
        predicted=("y_proba", "mean"),
        observed=("y_true", "mean"),
    )
    return table.reset_index()
