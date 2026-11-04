"""Testes da carga do ITAD, sem acesso à rede."""

import json
from datetime import date, datetime, timezone
from email.message import Message
from typing import Any
from urllib.error import HTTPError

import pytest

from ingestion import itad_history

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
HISTORY = [{"timestamp": "2026-09-25T19:17:47+02:00", "deal": {"cut": 50}}]


def http_error(headers: dict[str, str]) -> HTTPError:
    """Cria um erro 429 com os cabeçalhos indicados."""
    message = Message()
    for name, value in headers.items():
        message[name] = value
    return HTTPError("https://exemplo", 429, "limite", message, None)


def test_retry_wait_prefers_retry_after_header() -> None:
    assert itad_history.retry_wait(http_error({"Retry-After": "7"}), 2) == 7


def test_retry_wait_falls_back_to_backoff() -> None:
    assert itad_history.retry_wait(http_error({}), 1) == 60


def test_history_is_kept_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(itad_history, "request_json", lambda *_a, **_k: (200, HISTORY))

    row = itad_history.fetch_history(1, "id-itad", "chave")

    assert json.loads(row.raw_json) == HISTORY
    assert row.http_status == 200


def test_full_history_is_requested_for_brazil_steam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake(_path: str, _key: str, params: dict[str, Any]) -> tuple[int, Any]:
        calls.append(params)
        return 200, []

    monkeypatch.setattr(itad_history, "request_json", fake)

    itad_history.fetch_history(1, "id-itad", "chave")

    assert calls[0]["country"] == "BR"
    assert calls[0]["shops"] == 61
    assert calls[0]["since"] == "2000-01-01T00:00:00Z"


def test_empty_history_counts_as_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(itad_history, "request_json", lambda *_a, **_k: (200, []))

    row = itad_history.fetch_history(1, "id-itad", "chave")

    assert row.raw_json == "[]"


def test_game_without_itad_id_skips_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_a: Any, **_k: Any) -> None:
        raise AssertionError("Não deveria chamar a API")

    monkeypatch.setattr(itad_history, "request_json", fail)

    row = itad_history.fetch_history(1, None, "chave")

    assert row.itad_id is None
    assert row.raw_json is None


def test_failed_game_keeps_its_row_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(itad_history, "request_json", lambda *_a, **_k: (500, None))

    table = itad_history.build_table(
        [itad_history.fetch_history(1, "id-itad", "chave")]
    )

    assert table.schema == itad_history.BRONZE_SCHEMA
    assert table["raw_json"][0].as_py() is None
    assert table["http_status"][0].as_py() == 500


def test_lookup_failure_stops_the_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(itad_history, "request_json", lambda *_a, **_k: (500, None))

    with pytest.raises(RuntimeError):
        itad_history.lookup_game_ids([1], "chave")


def test_lookup_keeps_games_without_id(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"app/1": "id-itad", "app/2": None}
    monkeypatch.setattr(
        itad_history, "request_json", lambda *_a, **_k: (200, payload)
    )

    assert itad_history.lookup_game_ids([1, 2], "chave") == {1: "id-itad", 2: None}


def test_partition_path_is_fixed_for_the_day() -> None:
    path = itad_history.partition_path(date(2026, 11, 4))

    assert path == "itad_history/date=2026-11-04/data.parquet"
