"""Spike da Fase 0: preço BR da Steam via appdetails.

Tarefa 1: consulta 5 jogos, um por vez, e confirma se a moeda é BRL.
Usa só a biblioteca padrão. Execução: python spikes/steam_prices.py
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_URL = "https://store.steampowered.com/api/appdetails"
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


def fetch_price(app_id: int) -> tuple[int, dict[str, Any] | None]:
    """Busca o price_overview de um jogo e devolve (status HTTP, JSON)."""
    query = urllib.parse.urlencode(
        {"appids": app_id, "cc": "br", "filters": "price_overview"}
    )
    request = urllib.request.Request(
        f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None


def currency_of(app_id: int, payload: dict[str, Any] | None) -> str | None:
    """Extrai a moeda da resposta; None se o preço não veio."""
    if payload is None:
        return None
    entry = payload.get(str(app_id), {})
    if not entry.get("success"):
        return None
    data = entry.get("data") or {}
    return data.get("price_overview", {}).get("currency")


def main() -> int:
    """Consulta os jogos, mostra o JSON bruto e devolve 0 se tudo for BRL."""
    currencies: dict[int, str | None] = {}

    for position, (app_id, name) in enumerate(APP_IDS.items()):
        if position > 0:
            time.sleep(SECONDS_BETWEEN_REQUESTS)

        try:
            status, payload = fetch_price(app_id)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            # Falha de um jogo não interrompe a execução.
            print(f"\n--- {name} ({app_id}): falhou: {error!r}")
            currencies[app_id] = None
            continue

        print(f"\n--- {name} ({app_id}): HTTP {status}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        currencies[app_id] = currency_of(app_id, payload)

    print("\n=== Resumo ===")
    for app_id, currency in currencies.items():
        print(f"{APP_IDS[app_id]}: {currency}")

    all_ok = all(c == EXPECTED_CURRENCY for c in currencies.values())
    print(f"Todos em {EXPECTED_CURRENCY}: {all_ok}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
