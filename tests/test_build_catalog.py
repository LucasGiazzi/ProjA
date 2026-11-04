"""Testes da montagem do catálogo, sem acesso à rede."""

import csv
from pathlib import Path
from typing import Any

import pytest

from ingestion import build_catalog, steam_api
from ingestion.build_catalog import CatalogRow

PRICED = {"success": True, "data": {"price_overview": {"final": 100}}}
FREE = {"success": True, "data": []}


def test_wishlist_wins_when_game_is_in_both_sources() -> None:
    rows = build_catalog.build_rows({2: "B"}, {1: "A", 2: "B"})

    assert rows == [
        CatalogRow(1, "A", build_catalog.SOURCE_TOP_SELLER),
        CatalogRow(2, "B", build_catalog.SOURCE_WISHLIST),
    ]


def test_selection_drops_free_games_and_skips_wishlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [{1: "Pago", 2: "Gratis", 3: "Na wishlist"}, {4: "Pago 2", 5: "Pago 3"}]
    prices = {"1": PRICED, "2": FREE, "4": PRICED, "5": PRICED}

    def fake_page(start: int) -> dict[int, str]:
        return pages[start // steam_api.SEARCH_PAGE_SIZE]

    def fake_prices(app_ids: list[int]) -> tuple[dict[str, Any], dict[int, int]]:
        assert 3 not in app_ids
        return {str(i): prices[str(i)] for i in app_ids}, {}

    monkeypatch.setattr(steam_api, "fetch_top_sellers_page", fake_page)
    monkeypatch.setattr(steam_api, "fetch_prices", fake_prices)

    selected = build_catalog.select_paid_top_sellers(limit=2, skip={3})

    assert selected == {1: "Pago", 4: "Pago 2"}


def test_csv_keeps_names_with_commas(tmp_path: Path) -> None:
    path = tmp_path / "seeds" / "catalog.csv"

    build_catalog.write_catalog([CatalogRow(1, "Jogo, o Retorno", "topseller")], path)

    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows == [{"app_id": "1", "name": "Jogo, o Retorno", "source": "topseller"}]
