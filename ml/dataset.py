"""Leitura das features e divisão temporal de treino e teste."""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from ingestion.config import PROJECT_ROOT

DUCKDB_PATH = PROJECT_ROOT / "dbt" / "vale_esperar.duckdb"

TARGET = "has_sale_next_30d"
BASELINE = "baseline_prediction"
DATE_COLUMN = "price_date"

NUMERIC_FEATURES = [
    "days_since_last_sale",
    "avg_days_between_sales",
    "sales_to_date",
    "sales_last_12_months",
    "max_discount_to_date",
    "typical_discount",
    "days_to_next_seasonal",
    "days_since_release",
    "base_price_cents",
    "publisher_sale_rate",
    "discount_percent",
    "discount_vs_typical",
]
BOOLEAN_FEATURES = ["is_on_sale", "is_seasonal_sale_today", BASELINE]
CATEGORICAL_FEATURES = ["month"]
ALL_FEATURES = NUMERIC_FEATURES + BOOLEAN_FEATURES + CATEGORICAL_FEATURES

TRAIN_END = date(2024, 12, 31)
LABEL_WINDOW_DAYS = 30


def load_features(path: Path = DUCKDB_PATH) -> pd.DataFrame:
    """Lê as linhas com rótulo conhecido de ml_features."""
    query = f"select * from ml_features where {TARGET} is not null"
    with duckdb.connect(str(path), read_only=True) as connection:
        features = connection.execute(query).df()
    features[DATE_COLUMN] = pd.to_datetime(features[DATE_COLUMN])
    return features


def temporal_split(
    features: pd.DataFrame,
    train_end: date = TRAIN_END,
    label_window_days: int = LABEL_WINDOW_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa treino e teste no tempo, com um intervalo do tamanho da janela.

    O rótulo do último dia de treino olha 30 dias à frente; sem o intervalo,
    esses dias estariam também no teste.
    """
    test_start = train_end + timedelta(days=label_window_days + 1)
    dates = features[DATE_COLUMN].dt.date
    train = features[dates <= train_end]
    test = features[dates >= test_start]
    return train, test
