"""Testes da carga de dados cadastrais, sem acesso à rede."""

import json
from datetime import date, datetime, timezone
from typing import Any

import pytest

from ingestion import steam_details, steam_prices

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
ENTRY = {"success": True, "data": {"type": "game", "publishers": ["Editora"]}}


def test_entry_is_kept_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        steam_details.steam_api, "get_json", lambda *_: (200, {"10": ENTRY})
    )

    status, raw_json = steam_details.fetch_details(10)

    assert status == 200
    assert json.loads(raw_json) == ENTRY


def test_language_is_fixed_for_date_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(_url: str, params: dict[str, Any]) -> tuple[int, Any]:
        calls.append(params)
        return 200, {"10": ENTRY}

    monkeypatch.setattr(steam_details.steam_api, "get_json", fake)

    steam_details.fetch_details(10)

    assert calls[0]["l"] == "english"


def test_failed_game_keeps_its_row_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(steam_details.steam_api, "get_json", lambda *_: (500, None))

    status, raw_json = steam_details.fetch_details(10)
    table = steam_details.build_table([10], [status], [raw_json], NOW)

    assert table.schema == steam_prices.BRONZE_SCHEMA
    assert table["source"][0].as_py() == "steam_details"
    assert table["http_status"][0].as_py() == 500
    assert table["raw_json"][0].as_py() is None


def test_partition_path_is_fixed_for_the_day() -> None:
    path = steam_details.partition_path(date(2026, 11, 4))

    assert path == "steam_details/date=2026-11-04/data.parquet"
