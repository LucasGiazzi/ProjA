"""Spike da Fase 0: preço BR da Steam via appdetails.

Tarefa 1: consulta jogos um por vez e confirma se a moeda é BRL, incluindo
jogos em promoção hoje para observar o formato com desconto.
Tarefa 2: testa a consulta agrupada (appids=a,b,c), compara com a individual
e sobe o tamanho da chamada em degraus para achar o máximo.
Usa só a biblioteca padrão. Execução: python spikes/steam_prices.py
"""

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_URL = "https://store.steampowered.com/api/appdetails"
FEATURED_URL = "https://store.steampowered.com/api/featuredcategories"
SEARCH_URL = "https://store.steampowered.com/search/results/"
EXPECTED_CURRENCY = "BRL"
USER_AGENT = "vale-esperar-spike/0.1"
TIMEOUT_SECONDS = 30

# ~200 req / 5 min equivale a 1 req a cada 1,5 s.
SECONDS_BETWEEN_REQUESTS = 1.5

# Jogos pagos: jogos gratuitos não devem trazer price_overview.
APP_IDS: dict[int, str] = {
    1091500: "Cyberpunk 2077",
    1245620: "Elden Ring",
    292030: "The Witcher 3",
    413150: "Stardew Valley",
    1174180: "Red Dead Redemption 2",
}

ON_SALE_LIMIT = 3
SEARCH_PAGE_SIZE = 100

# Tamanhos testados na consulta agrupada.
BATCH_SIZES = (2, 5, 10, 25, 50, 100, 200, 300, 500, 750, 1000)

# Tamanhos candidatos para a coleta diária.
CHUNK_SIZES = (100, 50)

NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, ValueError)


def get_json(url: str, params: dict[str, Any]) -> tuple[int, Any]:
    """Faz um GET e devolve (status HTTP, JSON); erro HTTP vira (status, None)."""
    # safe="," mantém a vírgula literal em appids=a,b,c.
    query = urllib.parse.urlencode(params, safe=",")
    request = urllib.request.Request(
        f"{url}?{query}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


def fetch_prices(app_ids: list[int]) -> tuple[int, Any]:
    """Busca o price_overview de um ou mais jogos."""
    return get_json(
        API_URL,
        {
            "appids": ",".join(str(app_id) for app_id in app_ids),
            "cc": "br",
            "filters": "price_overview",
        },
    )


def fetch_on_sale_games(limit: int) -> dict[int, str]:
    """Busca jogos em promoção hoje; vitrine da Steam, muda todo dia."""
    _, payload = get_json(FEATURED_URL, {"cc": "br"})
    items = (payload or {}).get("specials", {}).get("items", [])
    on_sale = [item for item in items if item.get("discount_percent", 0) > 0]
    return {item["id"]: item["name"] for item in on_sale[:limit]}


def fetch_sample_ids(total: int) -> list[int]:
    """Monta uma lista de appids reais a partir da busca da loja."""
    app_ids: list[int] = []
    for start in range(0, total, SEARCH_PAGE_SIZE):
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        status, payload = get_json(
            SEARCH_URL,
            {
                "json": 1,
                "category1": 998,  # somente jogos
                "cc": "br",
                "filter": "topsellers",
                "count": SEARCH_PAGE_SIZE,
                "start": start,
            },
        )
        items = (payload or {}).get("items", [])
        print(f"busca start={start}: HTTP {status}, {len(items)} itens")
        if not items:
            break
        for item in items:
            # A busca não traz o appid; ele aparece na URL da imagem.
            match = re.search(r"/apps/(\d+)/", item.get("logo", ""))
            if match:
                app_ids.append(int(match.group(1)))
    return list(dict.fromkeys(app_ids))


def price_of(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extrai o price_overview de uma entrada; None se o preço não veio."""
    if not entry or not entry.get("success"):
        return None
    # Sem preço, "data" pode vir vazio.
    return (entry.get("data") or {}).get("price_overview")


def run_individual(games: dict[int, str]) -> dict[int, dict[str, Any] | None]:
    """Tarefa 1: consulta um jogo por chamada e mostra o JSON bruto."""
    prices: dict[int, dict[str, Any] | None] = {}

    for position, (app_id, name) in enumerate(games.items()):
        if position > 0:
            time.sleep(SECONDS_BETWEEN_REQUESTS)

        try:
            status, payload = fetch_prices([app_id])
        except NETWORK_ERRORS as error:
            # Falha de um jogo não interrompe a execução.
            print(f"\n--- {name} ({app_id}): falhou: {error!r}")
            prices[app_id] = None
            continue

        print(f"\n--- {name} ({app_id}): HTTP {status}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        prices[app_id] = price_of((payload or {}).get(str(app_id)))

    return prices


def compare_batch(individual: dict[int, dict[str, Any] | None]) -> None:
    """Tarefa 2: confere se o agrupado devolve o mesmo que o individual."""
    print("\n=== Agrupado vs. individual ===")
    time.sleep(SECONDS_BETWEEN_REQUESTS)
    status, payload = fetch_prices(list(individual))
    print(f"HTTP {status}, {len(payload or {})} jogos na resposta")

    for app_id, price in individual.items():
        batch_price = price_of((payload or {}).get(str(app_id)))
        print(f"{app_id}: {'igual' if batch_price == price else 'DIFERENTE'}")
        if batch_price != price:
            print(f"  individual: {price}\n  agrupado:   {batch_price}")


def summarize_batch(app_ids: list[int], payload: Any) -> str:
    """Resume uma resposta agrupada em contagens."""
    entries = payload if isinstance(payload, dict) else {}
    prices = [price_of(entries.get(str(app_id))) for app_id in app_ids]
    priced = [price for price in prices if price]
    brl = [price for price in priced if price.get("currency") == EXPECTED_CURRENCY]
    no_success = sum(1 for entry in entries.values() if not entry.get("success"))
    return (
        f"voltaram={len(entries)} sem_sucesso={no_success} "
        f"com_preco={len(priced)} em_brl={len(brl)} "
        f"com_desconto={sum(1 for p in priced if p.get('discount_percent'))}"
    )


def check_chunks(sample_ids: list[int], size: int) -> None:
    """Tarefa 2: divide a amostra em lotes, como a coleta diária faria."""
    chunks = [
        sample_ids[start : start + size]
        for start in range(0, len(sample_ids), size)
    ]
    failures: list[tuple[int, int]] = []
    returned = 0

    for position, chunk in enumerate(chunks):
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        try:
            status, payload = fetch_prices(chunk)
        except NETWORK_ERRORS as error:
            print(f"lote {position}: falhou: {error!r}")
            failures.append((position, 0))
            continue

        if status != 200 or not payload:
            failures.append((position, status))
        else:
            returned += len(payload)

    print(
        f"lotes de {size}: {len(chunks) - len(failures)}/{len(chunks)} ok, "
        f"{returned}/{len(sample_ids)} jogos, falhas (lote, HTTP): {failures}"
    )


def find_batch_limit(sample_ids: list[int]) -> None:
    """Tarefa 2: testa tamanhos crescentes, sem parar em HTTP 500."""
    print(f"\n=== Degraus da consulta agrupada ({len(sample_ids)} appids) ===")
    for size in BATCH_SIZES:
        if size > len(sample_ids):
            print(f"{size}: pulado, amostra insuficiente")
            continue

        time.sleep(SECONDS_BETWEEN_REQUESTS)
        app_ids = sample_ids[:size]
        url_length = len(",".join(str(app_id) for app_id in app_ids))
        try:
            status, payload = fetch_prices(app_ids)
        except NETWORK_ERRORS as error:
            print(f"{size}: falhou: {error!r}")
            return

        print(
            f"{size}: HTTP {status} tam_appids={url_length} "
            f"{summarize_batch(app_ids, payload)}"
        )
        if status == 429:
            # 429 é limite de requisição, não de tamanho.
            print("Parou: HTTP 429")
            return


def main() -> int:
    """Roda as tarefas 1 e 2; devolve 0 se as consultas individuais forem BRL."""
    on_sale = fetch_on_sale_games(ON_SALE_LIMIT)
    print(f"Em promoção hoje: {on_sale}")
    time.sleep(SECONDS_BETWEEN_REQUESTS)

    games = {**APP_IDS, **on_sale}
    prices = run_individual(games)

    print("\n=== Resumo individual ===")
    for app_id, price in prices.items():
        currency = price.get("currency") if price else None
        discount = price.get("discount_percent") if price else None
        print(f"{games[app_id]}: {currency}, desconto {discount}%")

    all_ok = all(p and p.get("currency") == EXPECTED_CURRENCY for p in prices.values())
    print(f"Todos em {EXPECTED_CURRENCY}: {all_ok}")

    compare_batch(prices)

    sample_ids = fetch_sample_ids(max(BATCH_SIZES))
    find_batch_limit(sample_ids)

    print("\n=== Cobertura em lotes ===")
    for size in CHUNK_SIZES:
        check_chunks(sample_ids, size)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
