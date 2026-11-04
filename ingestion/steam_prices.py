"""Coletor diário de preços da Steam: grava a resposta bruta na bronze.

Não transforma dados: guarda a entrada da Steam como veio, com metadados.
Reexecutar no mesmo dia sobrescreve a partição do dia, nunca duplica.
Execução: python -m ingestion.steam_prices
"""

import csv
import io
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import HfApi

from ingestion import steam_api
from ingestion.build_catalog import CATALOG_PATH
from ingestion.config import load_local_env, require_env

logger = logging.getLogger(__name__)

SOURCE = "steam_appdetails"
BRONZE_PREFIX = "steam_prices"

# Mesmo limite do teste de volume diário definido no design.
MIN_SUCCESS_RATE = 0.95

BRONZE_SCHEMA = pa.schema(
    [
        ("app_id", pa.int64()),
        ("raw_json", pa.string()),
        ("collected_at", pa.timestamp("us", tz="UTC")),
        ("source", pa.string()),
        ("http_status", pa.int32()),
    ]
)


def read_catalog(path: Path) -> list[int]:
    """Lê os appids do seed do catálogo."""
    with path.open(encoding="utf-8", newline="") as file:
        return [int(row["app_id"]) for row in csv.DictReader(file)]


def build_table(
    app_ids: list[int],
    entries: dict[str, Any],
    failed: dict[int, int],
    collected_at: datetime,
) -> pa.Table:
    """Monta a tabela bronze: uma linha por jogo do catálogo, inclusive falhas."""
    raw_entries = [entries.get(str(app_id)) for app_id in app_ids]
    return pa.table(
        {
            "app_id": app_ids,
            "raw_json": [
                None if entry is None else json.dumps(entry, ensure_ascii=False)
                for entry in raw_entries
            ],
            "collected_at": [collected_at] * len(app_ids),
            "source": [SOURCE] * len(app_ids),
            "http_status": [failed.get(app_id, 200) for app_id in app_ids],
        },
        schema=BRONZE_SCHEMA,
    )


def success_rate(table: pa.Table) -> float:
    """Calcula a fração de jogos com resposta da Steam."""
    if table.num_rows == 0:
        return 0.0
    return (table.num_rows - table["raw_json"].null_count) / table.num_rows


def partition_path(day: date) -> str:
    """Caminho da partição do dia; fixo para que reexecutar sobrescreva."""
    return f"{BRONZE_PREFIX}/date={day.isoformat()}/data.parquet"


def upload_table(table: pa.Table, path: str, repo_id: str, token: str) -> None:
    """Grava a tabela em Parquet no dataset do Hugging Face."""
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    HfApi(token=token).upload_file(
        path_or_fileobj=buffer.getvalue(),
        path_in_repo=path,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Coleta {path}",
    )


def main() -> int:
    """Coleta o catálogo e grava a partição do dia; 1 indica coleta incompleta."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_local_env()
    repo_id = require_env("HF_DATASET_REPO")
    token = require_env("HF_TOKEN")

    app_ids = read_catalog(CATALOG_PATH)
    collected_at = datetime.now(timezone.utc)
    entries, failed = steam_api.fetch_prices(app_ids)
    table = build_table(app_ids, entries, failed, collected_at)

    rate = success_rate(table)
    logger.info(
        "Coletados %d de %d jogos (%.1f%%), %d com falha",
        table.num_rows - table["raw_json"].null_count,
        table.num_rows,
        rate * 100,
        len(failed),
    )
    for app_id, status in failed.items():
        logger.warning("Jogo %d falhou: status %s", app_id, status)

    if rate == 0:
        # Não substitui uma partição boa por uma vazia.
        logger.error("Nenhum jogo coletado: nada foi gravado")
        return 1

    path = partition_path(collected_at.date())
    upload_table(table, path, repo_id, token)
    logger.info("Gravado: %s", path)

    if rate < MIN_SUCCESS_RATE:
        logger.error("Coleta abaixo de %.0f%%", MIN_SUCCESS_RATE * 100)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
