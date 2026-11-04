"""Carga única do histórico de preços do IsThereAnyDeal para a bronze.

Guarda o histórico completo como veio, uma linha por jogo. O corte de data e
o preenchimento acontecem no dbt. A chave vai no cabeçalho, nunca na URL.
Execução: python -m ingestion.itad_history
"""

import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, NamedTuple

import pyarrow as pa

from ingestion.build_catalog import CATALOG_PATH
from ingestion.config import load_local_env, require_env
from ingestion.steam_prices import read_catalog, success_rate, upload_table

logger = logging.getLogger(__name__)

API_URL = "https://api.isthereanydeal.com"
USER_AGENT = "vale-esperar/0.1"
TIMEOUT_SECONDS = 30

SOURCE = "itad_history"
BRONZE_PREFIX = "itad_history"
STEAM_SHOP_ID = 61
COUNTRY = "BR"

# O padrão da API são 3 meses; uma data antiga pede o histórico inteiro.
SINCE = "2000-01-01T00:00:00Z"
LOOKUP_BATCH_SIZE = 200

# Limite padrão do ITAD: 1000 req / 5 min.
SECONDS_BETWEEN_REQUESTS = 0.4
MAX_RETRIES = 3
BACKOFF_SECONDS = 30
HTTP_TOO_MANY_REQUESTS = 429
NETWORK_ERROR_STATUS = 0
PROGRESS_INTERVAL = 100

MIN_SUCCESS_RATE = 0.95

BRONZE_SCHEMA = pa.schema(
    [
        ("app_id", pa.int64()),
        ("itad_id", pa.string()),
        ("raw_json", pa.string()),
        ("collected_at", pa.timestamp("us", tz="UTC")),
        ("source", pa.string()),
        ("http_status", pa.int32()),
    ]
)


class HistoryRow(NamedTuple):
    """Uma linha da bronze: o histórico completo de um jogo."""

    app_id: int
    itad_id: str | None
    raw_json: str | None
    collected_at: datetime
    source: str
    http_status: int


def retry_wait(error: urllib.error.HTTPError, attempt: int) -> int:
    """Calcula a espera, preferindo o cabeçalho Retry-After do ITAD."""
    header = error.headers.get("Retry-After") if error.headers else None
    if header and header.isdigit():
        return int(header)
    return BACKOFF_SECONDS * 2**attempt


def request_json(
    path: str,
    api_key: str,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> tuple[int, Any]:
    """Chama a API com backoff; erro definitivo devolve (status, None)."""
    headers = {"User-Agent": USER_AGENT, "ITAD-API-Key": api_key}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    request = urllib.request.Request(f"{API_URL}{path}{query}", data, headers)

    status = NETWORK_ERROR_STATUS
    for attempt in range(MAX_RETRIES + 1):
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status = error.code
            if status != HTTP_TOO_MANY_REQUESTS or attempt == MAX_RETRIES:
                return status, None
            wait = retry_wait(error, attempt)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            status = NETWORK_ERROR_STATUS
            wait = BACKOFF_SECONDS * 2**attempt
            logger.warning("Falha de rede: %s", type(error).__name__)

        logger.warning("Status %s; nova tentativa em %s s", status, wait)
        time.sleep(wait)

    return status, None


def lookup_game_ids(app_ids: list[int], api_key: str) -> dict[int, str | None]:
    """Traduz appids para IDs do ITAD; falha na tradução interrompe a carga."""
    game_ids: dict[int, str | None] = {}
    for start in range(0, len(app_ids), LOOKUP_BATCH_SIZE):
        batch = app_ids[start : start + LOOKUP_BATCH_SIZE]
        status, payload = request_json(
            f"/lookup/id/shop/{STEAM_SHOP_ID}/v1",
            api_key,
            body=[f"app/{app_id}" for app_id in batch],
        )
        if status != 200 or payload is None:
            raise RuntimeError(f"Tradução de appids falhou: status {status}")
        game_ids.update({app_id: payload.get(f"app/{app_id}") for app_id in batch})
    return game_ids


def fetch_history(app_id: int, itad_id: str | None, api_key: str) -> HistoryRow:
    """Busca o histórico de um jogo; jogo sem ID do ITAD vira linha sem dados."""
    now = datetime.now(timezone.utc)
    if itad_id is None:
        return HistoryRow(app_id, None, None, now, SOURCE, 200)

    status, payload = request_json(
        "/games/history/v2",
        api_key,
        params={
            "id": itad_id,
            "country": COUNTRY,
            "shops": STEAM_SHOP_ID,
            "since": SINCE,
        },
    )
    raw_json = None if payload is None else json.dumps(payload, ensure_ascii=False)
    return HistoryRow(app_id, itad_id, raw_json, now, SOURCE, status)


def build_table(rows: list[HistoryRow]) -> pa.Table:
    """Monta a tabela bronze."""
    return pa.Table.from_pylist(
        [row._asdict() for row in rows], schema=BRONZE_SCHEMA
    )


def partition_path(day: date) -> str:
    """Caminho da carga; fixo por dia para que reexecutar sobrescreva."""
    return f"{BRONZE_PREFIX}/date={day.isoformat()}/data.parquet"


def main() -> int:
    """Busca o histórico do catálogo e grava; 1 indica carga incompleta."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_local_env()
    api_key = require_env("ITAD_API_KEY")
    repo_id = require_env("HF_DATASET_REPO")
    token = require_env("HF_TOKEN")

    app_ids = read_catalog(CATALOG_PATH)
    game_ids = lookup_game_ids(app_ids, api_key)
    missing = [app_id for app_id, game_id in game_ids.items() if game_id is None]
    logger.info("%d jogos sem ID no ITAD: %s", len(missing), missing)

    rows: list[HistoryRow] = []
    for position, app_id in enumerate(app_ids, start=1):
        rows.append(fetch_history(app_id, game_ids[app_id], api_key))
        if position % PROGRESS_INTERVAL == 0:
            logger.info("Progresso: %d de %d", position, len(app_ids))

    table = build_table(rows)
    rate = success_rate(table)
    failed = [row for row in rows if row.raw_json is None and row.itad_id]
    logger.info("Histórico de %.1f%% dos jogos, %d com falha", rate * 100, len(failed))
    for row in failed:
        logger.warning("Jogo %d falhou: status %s", row.app_id, row.http_status)

    if rate == 0:
        logger.error("Nenhum histórico coletado: nada foi gravado")
        return 1

    path = partition_path(datetime.now(timezone.utc).date())
    upload_table(table, path, repo_id, token)
    logger.info("Gravado: %s", path)

    if rate < MIN_SUCCESS_RATE:
        logger.error("Carga abaixo de %.0f%%", MIN_SUCCESS_RATE * 100)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
