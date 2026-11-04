"""Gera o seed do catálogo: jogos pagos mais vendidos + wishlist do autor.

Roda só na criação e na revisão mensal do catálogo; a coleta diária lê o CSV.
Execução: python -m ingestion.build_catalog
"""

import csv
import logging
from pathlib import Path
from typing import NamedTuple

from ingestion import steam_api
from ingestion.config import PROJECT_ROOT, load_local_env, require_env

logger = logging.getLogger(__name__)

CATALOG_PATH = PROJECT_ROOT / "dbt" / "seeds" / "catalog.csv"
TARGET_SIZE = 500
MAX_SEARCH_PAGES = 20

SOURCE_TOP_SELLER = "topseller"
SOURCE_WISHLIST = "wishlist"


class CatalogRow(NamedTuple):
    """Uma linha do catálogo."""

    app_id: int
    name: str
    source: str


def select_paid_top_sellers(limit: int, skip: set[int]) -> dict[int, str]:
    """Percorre os mais vendidos e guarda só os jogos com preço."""
    selected: dict[int, str] = {}

    for page in range(MAX_SEARCH_PAGES):
        games = steam_api.fetch_top_sellers_page(page * steam_api.SEARCH_PAGE_SIZE)
        if not games:
            break

        candidates = [app_id for app_id in games if app_id not in skip | set(selected)]
        entries, failed = steam_api.fetch_prices(candidates)
        if failed:
            logger.warning("Página %d: %d jogos sem resposta", page, len(failed))

        for app_id in candidates:
            if steam_api.has_price(entries.get(str(app_id))):
                selected[app_id] = games[app_id]
            if len(selected) == limit:
                return selected

    logger.warning("Só %d de %d jogos pagos encontrados", len(selected), limit)
    return selected


def fetch_wishlist_names(app_ids: list[int]) -> dict[int, str]:
    """Busca os nomes da wishlist, que a API devolve só com appids."""
    names: dict[int, str] = {}
    for app_id in app_ids:
        name = steam_api.fetch_game_name(app_id)
        if name is None:
            logger.warning("Jogo %d da wishlist sem nome na loja", app_id)
        names[app_id] = name or ""
    return names


def build_rows(wishlist: dict[int, str], top_sellers: dict[int, str]) -> list[CatalogRow]:
    """Une as origens; a wishlist vence, e a ordem por appid estabiliza o diff."""
    rows = [
        CatalogRow(app_id, name, SOURCE_TOP_SELLER)
        for app_id, name in top_sellers.items()
        if app_id not in wishlist
    ]
    rows += [
        CatalogRow(app_id, name, SOURCE_WISHLIST) for app_id, name in wishlist.items()
    ]
    return sorted(rows)


def write_catalog(rows: list[CatalogRow], path: Path) -> None:
    """Grava o catálogo em CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(CatalogRow._fields)
        writer.writerows(rows)


def main() -> None:
    """Monta o catálogo; wishlist vazia interrompe, para não perder esses jogos."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_local_env()

    wishlist_ids = steam_api.fetch_wishlist(require_env("STEAM_ID"))
    if not wishlist_ids:
        raise RuntimeError("Wishlist vazia: confira se o perfil está público")

    wishlist = fetch_wishlist_names(wishlist_ids)
    top_sellers = select_paid_top_sellers(TARGET_SIZE - len(wishlist), set(wishlist))
    rows = build_rows(wishlist, top_sellers)
    write_catalog(rows, CATALOG_PATH)
    logger.info(
        "Catálogo: %d jogos (%d da wishlist, %d mais vendidos)",
        len(rows),
        len(wishlist),
        len(top_sellers),
    )


if __name__ == "__main__":
    main()
