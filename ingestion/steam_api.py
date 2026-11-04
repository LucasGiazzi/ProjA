"""Cliente da Steam: pausa entre chamadas, backoff e consulta em lotes."""

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
SEARCH_URL = "https://store.steampowered.com/search/results/"
WISHLIST_URL = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"

USER_AGENT = "vale-esperar/0.1"
TIMEOUT_SECONDS = 30

# ~200 req / 5 min equivale a 1 req a cada 1,5 s.
SECONDS_BETWEEN_REQUESTS = 1.5
MAX_RETRIES = 3
BACKOFF_SECONDS = 30
HTTP_TOO_MANY_REQUESTS = 429
NETWORK_ERROR_STATUS = 0

# Lotes maiores falham de forma imprevisível (ver spikes/FINDINGS.md).
BATCH_SIZE = 50
SEARCH_PAGE_SIZE = 100
GAMES_CATEGORY = 998


def get_json(url: str, params: dict[str, Any]) -> tuple[int, Any]:
    """Faz um GET com backoff; erro definitivo devolve (status, None).

    A URL nunca vai para o log, porque pode conter o SteamID.
    """
    # safe="," mantém a vírgula literal em appids=a,b,c.
    query = urllib.parse.urlencode(params, safe=",")
    request = urllib.request.Request(
        f"{url}?{query}", headers={"User-Agent": USER_AGENT}
    )

    status = NETWORK_ERROR_STATUS
    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            wait = BACKOFF_SECONDS * 2 ** (attempt - 1)
            logger.warning("Status %s; nova tentativa em %s s", status, wait)
            time.sleep(wait)

        time.sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status = error.code
            if status != HTTP_TOO_MANY_REQUESTS:
                return status, None
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            status = NETWORK_ERROR_STATUS
            logger.warning("Falha de rede: %s", type(error).__name__)

    return status, None


def chunked(items: list[int], size: int) -> list[list[int]]:
    """Divide uma lista em pedaços de até `size` itens."""
    return [items[start : start + size] for start in range(0, len(items), size)]


def fetch_price_batch(app_ids: list[int]) -> tuple[dict[str, Any], dict[int, int]]:
    """Busca um lote; em falha, divide ao meio para isolar o problema.

    Devolve (entradas por appid, {appid que falhou: status HTTP}).
    Um 429 não divide o lote, porque isso só aumentaria o número de chamadas.
    """
    status, payload = get_json(
        APPDETAILS_URL,
        {
            "appids": ",".join(str(app_id) for app_id in app_ids),
            "cc": "br",
            "filters": "price_overview",
        },
    )
    if status == 200 and payload:
        return payload, {}

    logger.warning("Lote de %d jogos falhou: status %s", len(app_ids), status)
    if len(app_ids) == 1 or status == HTTP_TOO_MANY_REQUESTS:
        return {}, {app_id: status for app_id in app_ids}

    middle = len(app_ids) // 2
    left_entries, left_failed = fetch_price_batch(app_ids[:middle])
    right_entries, right_failed = fetch_price_batch(app_ids[middle:])
    return {**left_entries, **right_entries}, {**left_failed, **right_failed}


def fetch_prices(app_ids: list[int]) -> tuple[dict[str, Any], dict[int, int]]:
    """Busca os preços em lotes; a falha de um lote não interrompe os demais."""
    entries: dict[str, Any] = {}
    failed: dict[int, int] = {}
    for batch in chunked(app_ids, BATCH_SIZE):
        batch_entries, batch_failed = fetch_price_batch(batch)
        entries.update(batch_entries)
        failed.update(batch_failed)
    return entries, failed


def has_price(entry: dict[str, Any] | None) -> bool:
    """Indica se a entrada tem preço; sem preço, "data" vem como lista vazia."""
    if not entry or not entry.get("success"):
        return False
    return bool((entry.get("data") or {}).get("price_overview"))


def fetch_top_sellers_page(start: int) -> dict[int, str]:
    """Busca uma página dos mais vendidos no Brasil: {appid: nome}."""
    status, payload = get_json(
        SEARCH_URL,
        {
            "json": 1,
            "category1": GAMES_CATEGORY,
            "cc": "br",
            "filter": "topsellers",
            "count": SEARCH_PAGE_SIZE,
            "start": start,
        },
    )
    if status != 200 or not payload:
        raise RuntimeError(f"Busca da loja falhou: status {status}")

    games: dict[int, str] = {}
    for item in payload.get("items", []):
        # A busca não traz o appid; ele aparece na URL da imagem.
        match = re.search(r"/apps/(\d+)/", item.get("logo", ""))
        if match:
            games.setdefault(int(match.group(1)), item.get("name", ""))
    return games


def fetch_wishlist(steam_id: str) -> list[int]:
    """Busca os appids da wishlist de um perfil público."""
    status, payload = get_json(WISHLIST_URL, {"steamid": steam_id})
    if status != 200 or not payload:
        raise RuntimeError(f"Wishlist falhou: status {status}")
    items = payload.get("response", {}).get("items", [])
    return [item["appid"] for item in items]


def fetch_game_name(app_id: int) -> str | None:
    """Busca o nome de um jogo; None se a loja não devolver."""
    status, payload = get_json(
        APPDETAILS_URL, {"appids": app_id, "cc": "br", "filters": "basic"}
    )
    entry = (payload or {}).get(str(app_id)) or {}
    if status != 200 or not entry.get("success"):
        return None
    return (entry.get("data") or {}).get("name")
