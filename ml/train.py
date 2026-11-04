"""Treina a regressão logística e compara com as regras de referência.

Execução: python -m ml.train
Requer o banco local gerado por `dbt build`.
"""

import logging
from typing import Any

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ingestion.config import PROJECT_ROOT
from ml.dataset import (
    ALL_FEATURES,
    BASELINE,
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    TRAIN_END,
    load_features,
    temporal_split,
)
from ml.evaluate import calibration_table, classification_metrics
from ml.report import (
    MODEL_NAME,
    ReportData,
    Results,
    calibration_markdown,
    metrics_table,
    write_report,
    yearly_table,
)

logger = logging.getLogger(__name__)

MLFLOW_URI = f"sqlite:///{(PROJECT_ROOT / 'ml' / 'mlflow.db').as_posix()}"
MLFLOW_EXPERIMENT = "vale-esperar-promocao"
REPORT_PATH = PROJECT_ROOT / "docs" / "model_report.md"
SKOPS_TRUSTED_TYPES = ["numpy.dtype"]

MODEL_PARAMS: dict[str, Any] = {"C": 1.0, "max_iter": 1000}


def build_model() -> Pipeline:
    """Monta o pré-processamento e a regressão logística."""
    numeric = make_pipeline(
        # Nulo tem significado aqui: o jogo ainda não teve promoção, por exemplo.
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
    )
    preprocess = ColumnTransformer(
        [
            ("numeric", numeric, NUMERIC_FEATURES),
            ("boolean", "passthrough", BOOLEAN_FEATURES),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL_FEATURES,
            ),
        ]
    )
    return make_pipeline(preprocess, LogisticRegression(**MODEL_PARAMS))


def prepare_inputs(features: pd.DataFrame) -> pd.DataFrame:
    """Seleciona as colunas do modelo, com booleanos em formato numérico."""
    inputs = features[ALL_FEATURES].copy()
    inputs[BOOLEAN_FEATURES] = inputs[BOOLEAN_FEATURES].astype(float)
    inputs[NUMERIC_FEATURES] = inputs[NUMERIC_FEATURES].astype(float)
    return inputs


def reference_predictions(
    train: pd.DataFrame, test: pd.DataFrame
) -> dict[str, np.ndarray]:
    """Gera as regras simples que o modelo precisa superar."""
    baseline = test[BASELINE].to_numpy(dtype=bool)
    train_rates = train.groupby(BASELINE)[TARGET].mean()
    return {
        "Sempre sim": np.ones(len(test)),
        "Baseline sazonal": baseline.astype(float),
        # Mesma regra em probabilidade, para o Brier não punir a resposta 0 ou 1.
        "Baseline sazonal calibrado": test[BASELINE].map(train_rates).to_numpy(dtype=float),
    }


def compare(test: pd.DataFrame, predictions: dict[str, np.ndarray]) -> Results:
    """Calcula as métricas de cada abordagem, nas linhas do teste recebidas."""
    y_true = test[TARGET].to_numpy(dtype=bool)
    return {
        name: classification_metrics(y_true, y_proba)
        for name, y_proba in predictions.items()
    }


def log_to_mlflow(model: Pipeline, full_price: Results, all_rows: Results) -> None:
    """Registra parâmetros, métricas, relatório e modelo no MLflow local."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    with mlflow.start_run(run_name="logistic_regression"):
        mlflow.log_params({**MODEL_PARAMS, "train_end": str(TRAIN_END)})
        mlflow.log_metrics(
            {f"full_price_{key}": value for key, value in full_price[MODEL_NAME].items()}
        )
        mlflow.log_metrics(
            {f"all_rows_{key}": value for key, value in all_rows[MODEL_NAME].items()}
        )
        mlflow.log_artifact(str(REPORT_PATH))
        # Tipo básico do numpy, em um modelo treinado aqui mesmo.
        mlflow.sklearn.log_model(
            model, name="model", skops_trusted_types=SKOPS_TRUSTED_TYPES
        )


def main() -> None:
    """Treina, avalia, grava o relatório e registra no MLflow."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    features = load_features()
    train, test = temporal_split(features)
    logger.info("Treino: %d linhas; teste: %d linhas", len(train), len(test))

    model = build_model()
    model.fit(prepare_inputs(train), train[TARGET].to_numpy(dtype=bool))

    predictions = reference_predictions(train, test)
    predictions[MODEL_NAME] = model.predict_proba(prepare_inputs(test))[:, 1]

    is_full_price = ~test["is_on_sale"].to_numpy(dtype=bool)
    full_price_test = test[is_full_price]
    full_price_predictions = {
        name: values[is_full_price] for name, values in predictions.items()
    }
    full_price = compare(full_price_test, full_price_predictions)
    all_rows = compare(test, predictions)

    is_unseen = ~full_price_test["app_id"].isin(train["app_id"]).to_numpy()
    unseen_test = full_price_test[is_unseen]
    unseen_games = compare(
        unseen_test,
        {name: values[is_unseen] for name, values in full_price_predictions.items()},
    )

    calibration = calibration_table(
        full_price_test[TARGET].to_numpy(dtype=bool),
        full_price_predictions[MODEL_NAME],
    )
    write_report(
        REPORT_PATH,
        ReportData(
            train_end=TRAIN_END,
            train=train,
            test=test,
            full_price=full_price,
            all_rows=all_rows,
            unseen_games=unseen_games,
            unseen_game_count=unseen_test["app_id"].nunique(),
            yearly=yearly_table(test, predictions),
            calibration=calibration_markdown(calibration),
        ),
    )
    logger.info("Relatório: %s", REPORT_PATH)

    log_to_mlflow(model, full_price, all_rows)
    logger.info("\n%s", metrics_table(full_price))


if __name__ == "__main__":
    main()
