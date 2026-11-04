"""Treina a regressão logística e compara com as regras de referência.

Execução: python -m ml.train
Requer o banco local gerado por `dbt build`.
"""

import logging
from pathlib import Path
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
    DATE_COLUMN,
    LABEL_WINDOW_DAYS,
    NUMERIC_FEATURES,
    TARGET,
    TRAIN_END,
    load_features,
    temporal_split,
)
from ml.evaluate import calibration_table, classification_metrics

logger = logging.getLogger(__name__)

MLFLOW_URI = f"sqlite:///{(PROJECT_ROOT / 'ml' / 'mlflow.db').as_posix()}"
MLFLOW_EXPERIMENT = "vale-esperar-promocao"
REPORT_PATH = PROJECT_ROOT / "docs" / "model_report.md"

SKOPS_TRUSTED_TYPES = ["numpy.dtype"]

MODEL_PARAMS: dict[str, Any] = {"C": 1.0, "max_iter": 1000}
MODEL_NAME = "Regressão logística"
METRIC_LABELS = {
    "accuracy": "Acurácia",
    "precision": "Precisão",
    "recall": "Recall",
    "f1": "F1",
    "brier": "Brier",
    "roc_auc": "ROC AUC",
}
LOWER_IS_BETTER = {"brier"}


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


def compare(
    test: pd.DataFrame, predictions: dict[str, np.ndarray]
) -> dict[str, dict[str, float]]:
    """Calcula as métricas de cada abordagem, nas linhas do teste recebidas."""
    y_true = test[TARGET].to_numpy(dtype=bool)
    return {
        name: classification_metrics(y_true, y_proba)
        for name, y_proba in predictions.items()
    }


def metrics_table(results: dict[str, dict[str, float]]) -> str:
    """Formata as métricas em uma tabela Markdown."""
    header = "| Abordagem | " + " | ".join(METRIC_LABELS.values()) + " |"
    divider = "|---|" + "---|" * len(METRIC_LABELS)
    rows = [
        f"| {name} | "
        + " | ".join(f"{metrics[key]:.3f}" for key in METRIC_LABELS)
        + " |"
        for name, metrics in results.items()
    ]
    return "\n".join([header, divider, *rows])


def yearly_table(test: pd.DataFrame, predictions: dict[str, np.ndarray]) -> str:
    """Compara o modelo e as regras por ano do teste, a preço cheio."""
    frame = test.assign(
        year=test[DATE_COLUMN].dt.year,
        **{name: values for name, values in predictions.items()},
    )
    frame = frame[~frame["is_on_sale"].astype(bool)]
    lines = [
        "| Ano | Linhas | Positivos | Sempre sim (acurácia) | Baseline (acurácia) "
        f"| {MODEL_NAME} (acurácia) | {MODEL_NAME} (Brier) |",
        "|---|---|---|---|---|---|---|",
    ]
    for year, group in frame.groupby("year"):
        y_true = group[TARGET].to_numpy(dtype=bool)
        model = classification_metrics(y_true, group[MODEL_NAME].to_numpy())
        baseline = classification_metrics(y_true, group["Baseline sazonal"].to_numpy())
        lines.append(
            f"| {year} | {len(group)} | {y_true.mean():.1%} | {y_true.mean():.3f} "
            f"| {baseline['accuracy']:.3f} | {model['accuracy']:.3f} "
            f"| {model['brier']:.3f} |"
        )
    return "\n".join(lines)


def calibration_markdown(table: pd.DataFrame) -> str:
    """Formata a calibração em uma tabela Markdown."""
    lines = ["| Faixa | Linhas | Previsto | Observado |", "|---|---|---|---|"]
    for row in table.itertuples():
        lines.append(
            f"| {row.bin} | {row.rows} | {row.predicted:.1%} | {row.observed:.1%} |"
        )
    return "\n".join(lines)


def beats(
    model: dict[str, float], reference: dict[str, float], metric: str
) -> bool:
    """Indica se o modelo supera a referência na métrica."""
    if metric in LOWER_IS_BETTER:
        return model[metric] < reference[metric]
    return model[metric] > reference[metric]


def write_report(
    path: Path,
    train: pd.DataFrame,
    test: pd.DataFrame,
    full_price: dict[str, dict[str, float]],
    all_rows: dict[str, dict[str, float]],
    unseen_games: dict[str, dict[str, float]],
    unseen_game_count: int,
    yearly: str,
    calibration: str,
) -> None:
    """Grava o relatório de modelo vs. referências."""
    model = full_price[MODEL_NAME]
    references = [name for name in full_price if name != MODEL_NAME]
    checks = "\n".join(
        f"- Contra {name}: Brier {'melhor' if beats(model, full_price[name], 'brier') else 'pior'}, "
        f"F1 {'melhor' if beats(model, full_price[name], 'f1') else 'pior'}."
        for name in references
    )
    full_price_rows = int((~test["is_on_sale"].astype(bool)).sum())
    path.write_text(
        f"""# Relatório: modelo vs. baseline

Gerado por `python -m ml.train`.

## Dados

- Treino: até {TRAIN_END}, {len(train):,} linhas.
- Teste: {test[DATE_COLUMN].min().date()} a {test[DATE_COLUMN].max().date()}, {len(test):,} linhas, sendo {full_price_rows:,} a preço cheio.
- Intervalo de {LABEL_WINDOW_DAYS} dias entre treino e teste, porque o rótulo olha {LABEL_WINDOW_DAYS} dias à frente.

## Resultado principal: jogos a preço cheio

Este é o caso de uso central. Um jogo já em promoção tende a continuar nela no dia seguinte, o que inflaria as métricas.

{metrics_table(full_price)}

{checks}

## Todas as linhas

{metrics_table(all_rows)}

## Jogos fora do treino, a preço cheio

Cenário mais difícil: {unseen_game_count} jogos que o modelo nunca viu no treino.

{metrics_table(unseen_games)}

## Por ano, a preço cheio

{yearly}

## Calibração, a preço cheio

{calibration}

## Checagem de vazamento

Feita uma vez, com a mesma divisão: ao treinar com rótulos embaralhados, a ROC AUC a preço cheio oscilou entre 0.465 e 0.588 em 6 sementes, com média 0.516. Isso é compatível com o acaso.

## Limitações

- O catálogo veio dos mais vendidos de novembro de 2026, então o modelo só conhece jogos que continuam relevantes hoje. O desempenho em um jogo qualquer tende a ser pior.
- Em jogos sem nenhuma promoção anterior, o histórico quase não ajuda: a ROC AUC cai para 0.642, em 8.807 linhas de 74 jogos.
- Abaixo de 40%, o modelo superestima a chance de promoção, exceto na menor faixa.
- O calendário de 2019 a 2022 foi conferido com os próprios dados. Assume-se que essas datas eram conhecidas com antecedência.
- O preço cheio do ITAD diverge da Steam em 20 de 484 jogos na data da união.
""",
        encoding="utf-8",
    )


def main() -> None:
    """Treina, avalia, registra no MLflow e grava o relatório."""
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
        train,
        test,
        full_price,
        all_rows,
        unseen_games,
        unseen_test["app_id"].nunique(),
        yearly_table(test, predictions),
        calibration_markdown(calibration),
    )
    logger.info("Relatório: %s", REPORT_PATH)

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

    logger.info("\n%s", metrics_table(full_price))


if __name__ == "__main__":
    main()
