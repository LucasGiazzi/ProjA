"""Testes do coletor de preços, sem acesso à rede."""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from ingestion import steam_prices

COLLECTED_AT = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
ENTRY = {"success": True, "data": {"price_overview": {"final": 7495}}}
FREE_ENTRY = {"success": True, "data": []}


def test_raw_entry_is_kept_unchanged() -> None:
    table = steam_prices.build_table([1], {"1": ENTRY}, {}, COLLECTED_AT)

    assert json.loads(table["raw_json"][0].as_py()) == ENTRY


def test_table_has_bronze_schema_and_metadata() -> None:
    table = steam_prices.build_table([1], {"1": ENTRY}, {}, COLLECTED_AT)

    assert table.schema == steam_prices.BRONZE_SCHEMA
    assert table["source"][0].as_py() == "steam_appdetails"
    assert table["http_status"][0].as_py() == 200
    # Compara o inteiro gravado: as_py() exigiria base de fusos no Windows.
    microseconds = table["collected_at"].cast(pa.int64())[0].as_py()
    assert microseconds == int(COLLECTED_AT.timestamp() * 1_000_000)


def test_failed_game_keeps_its_row_and_status() -> None:
    entries = {"1": ENTRY}

    table = steam_prices.build_table([1, 2], entries, {2: 500}, COLLECTED_AT)

    assert table["app_id"].to_pylist() == [1, 2]
    assert table["raw_json"][1].as_py() is None
    assert table["http_status"].to_pylist() == [200, 500]


def test_game_without_price_counts_as_collected() -> None:
    table = steam_prices.build_table([1], {"1": FREE_ENTRY}, {}, COLLECTED_AT)

    assert steam_prices.success_rate(table) == 1.0


@pytest.mark.parametrize(
    ("app_ids", "entries", "expected"),
    [
        ([1, 2], {"1": ENTRY, "2": ENTRY}, 1.0),
        ([1, 2], {"1": ENTRY}, 0.5),
        ([1, 2], {}, 0.0),
        ([], {}, 0.0),
    ],
)
def test_success_rate(
    app_ids: list[int], entries: dict[str, Any], expected: float
) -> None:
    table = steam_prices.build_table(app_ids, entries, {}, COLLECTED_AT)

    assert steam_prices.success_rate(table) == expected


def test_partition_path_is_fixed_for_the_day() -> None:
    path = steam_prices.partition_path(date(2026, 11, 4))

    assert path == "steam_prices/date=2026-11-04/data.parquet"


def test_read_catalog_returns_app_ids(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text("app_id,name,source\n10,A,topseller\n20,B,wishlist\n", "utf-8")

    assert steam_prices.read_catalog(path) == [10, 20]


class FakeRun:
    """Isola o main da rede e registra os uploads."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, entries: dict[str, Any]) -> None:
        self.uploads: list[str] = []
        monkeypatch.setenv("HF_DATASET_REPO", "user/repo")
        monkeypatch.setenv("HF_TOKEN", "token-de-teste")
        monkeypatch.setattr(steam_prices, "load_local_env", lambda: None)
        monkeypatch.setattr(steam_prices, "read_catalog", lambda _: [1, 2])
        monkeypatch.setattr(
            steam_prices.steam_api, "fetch_prices", lambda _: (entries, {})
        )
        monkeypatch.setattr(
            steam_prices,
            "upload_table",
            lambda _table, path, *_: self.uploads.append(path),
        )


def test_main_does_not_write_when_nothing_was_collected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(monkeypatch, entries={})

    assert steam_prices.main() == 1
    assert run.uploads == []


def test_main_writes_partial_data_but_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(monkeypatch, entries={"1": ENTRY})

    assert steam_prices.main() == 1
    assert len(run.uploads) == 1


def test_main_succeeds_on_complete_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = FakeRun(monkeypatch, entries={"1": ENTRY, "2": ENTRY})

    assert steam_prices.main() == 0
    assert len(run.uploads) == 1
