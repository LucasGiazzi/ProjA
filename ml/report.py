"""Formata e grava o relatório de modelo vs. referências."""

from datetime import date
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

from ml.dataset import DATE_COLUMN, LABEL_WINDOW_DAYS, TARGET
from ml.evaluate import classification_metrics

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

Results = dict[str, dict[str, float]]


class ReportData(NamedTuple):
    """Tudo o que o relatório mostra."""

    train_end: date
    train: pd.DataFrame
    test: pd.DataFrame
    full_price: Results
    all_rows: Results
    unseen_games: Results
    unseen_game_count: int
    yearly: str
    calibration: str


def metrics_table(results: Results) -> str:
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


def beats(model: dict[str, float], reference: dict[str, float], metric: str) -> bool:
    """Indica se o modelo supera a referência na métrica."""
    if metric in LOWER_IS_BETTER:
        return model[metric] < reference[metric]
    return model[metric] > reference[metric]


def write_report(path: Path, data: ReportData) -> None:
    """Grava o relatório em Markdown."""
    model = data.full_price[MODEL_NAME]
    references = [name for name in data.full_price if name != MODEL_NAME]
    checks = "\n".join(
        f"- Contra {name}: Brier {'melhor' if beats(model, data.full_price[name], 'brier') else 'pior'}, "
        f"F1 {'melhor' if beats(model, data.full_price[name], 'f1') else 'pior'}."
        for name in references
    )
    test = data.test
    full_price_rows = int((~test["is_on_sale"].astype(bool)).sum())
    path.write_text(
        f"""# Relatório: modelo vs. baseline

Gerado por `python -m ml.train`.

## Dados

- Treino: até {data.train_end}, {len(data.train):,} linhas.
- Teste: {test[DATE_COLUMN].min().date()} a {test[DATE_COLUMN].max().date()}, {len(test):,} linhas, sendo {full_price_rows:,} a preço cheio.
- Intervalo de {LABEL_WINDOW_DAYS} dias entre treino e teste, porque o rótulo olha {LABEL_WINDOW_DAYS} dias à frente.

## Resultado principal: jogos a preço cheio

Este é o caso de uso central. Um jogo já em promoção tende a continuar nela no dia seguinte, o que inflaria as métricas.

{metrics_table(data.full_price)}

{checks}

## Todas as linhas

{metrics_table(data.all_rows)}

## Jogos fora do treino, a preço cheio

Cenário mais difícil: {data.unseen_game_count} jogos que o modelo nunca viu no treino.

{metrics_table(data.unseen_games)}

## Por ano, a preço cheio

{data.yearly}

## Calibração, a preço cheio

{data.calibration}

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
