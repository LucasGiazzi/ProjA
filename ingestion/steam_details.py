"""Carga única dos dados cadastrais dos jogos para a bronze.

Guarda a resposta da Steam como veio. Esta consulta não aceita lote, então faz
uma chamada por jogo. Roda na criação e na revisão mensal do catálogo.
Execução: python -m ingestion.steam_details
"""

import json
import logging
import sys
from datetime import date, datetime, timezone

import pyarrow as pa

from ingestion import steam_api
from ingestion.build_catalog import CATALOG_PATH
from ingestion.config import load_local_env, require_env
from ingestion.steam_prices import (
    BRONZE_SCHEMA,
    MIN_SUCCESS_RATE,
    read_catalog,
    success_rate,
    upload_table,
)

logger = logging.getLogger(__name__)

SOURCE = "steam_details"
BRONZE_PREFIX = "steam_details"
DETAILS_FILTERS = "basic,release_date,publishers,developers,genres"
PROGRESS_INTERVAL = 100


def fetch_details(app_id: int) -> tuple[int, str | None]:
    """Busca os dados de um jogo e devolve (status, JSON bruto)."""
    # l=english fixa o idioma, para a data de lançamento ter formato único.
    status, payload = steam_api.get_json(
        steam_api.APPDETAILS_URL,
        {"appids": app_id, "cc": "br", "l": "english", "filters": DETAILS_FILTERS},
    )
    entry = (payload or {}).get(str(app_id))
    return status, None if entry is None else json.dumps(entry, ensure_ascii=False)


def build_table(
    app_ids: list[int],
    statuses: list[int],
    raw_entries: list[str | None],
    collected_at: datetime,
) -> pa.Table:
    """Monta a tabela bronze, no mesmo formato da coleta de preços."""
    return pa.table(
        {
            "app_id": app_ids,
            "raw_json": raw_entries,
            "collected_at": [collected_at] * len(app_ids),
            "source": [SOURCE] * len(app_ids),
            "http_status": statuses,
        },
        schema=BRONZE_SCHEMA,
    )


def partition_path(day: date) -> str:
    """Caminho da carga; fixo por dia para que reexecutar sobrescreva."""
    return f"{BRONZE_PREFIX}/date={day.isoformat()}/data.parquet"


def main() -> int:
    """Busca os dados do catálogo e grava; 1 indica carga incompleta."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_local_env()
    repo_id = require_env("HF_DATASET_REPO")
    token = require_env("HF_TOKEN")

    app_ids = read_catalog(CATALOG_PATH)
    collected_at = datetime.now(timezone.utc)
    statuses: list[int] = []
    raw_entries: list[str | None] = []

    for position, app_id in enumerate(app_ids, start=1):
        status, raw_json = fetch_details(app_id)
        statuses.append(status)
        raw_entries.append(raw_json)
        if raw_json is None:
            logger.warning("Jogo %d falhou: status %s", app_id, status)
        if position % PROGRESS_INTERVAL == 0:
            logger.info("Progresso: %d de %d", position, len(app_ids))

    table = build_table(app_ids, statuses, raw_entries, collected_at)
    rate = success_rate(table)
    logger.info("Dados de %.1f%% dos jogos", rate * 100)

    if rate == 0:
        logger.error("Nenhum jogo coletado: nada foi gravado")
        return 1

    path = partition_path(collected_at.date())
    upload_table(table, path, repo_id, token)
    logger.info("Gravado: %s", path)

    if rate < MIN_SUCCESS_RATE:
        logger.error("Carga abaixo de %.0f%%", MIN_SUCCESS_RATE * 100)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
