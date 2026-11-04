"""Spike da Fase 0: histórico de preços no IsThereAnyDeal (ITAD).

Tarefa 4: busca o histórico de 3 jogos na loja Steam e mede a profundidade
e a moeda, com BR e com US para comparação.
A chave vem de ITAD_API_KEY (ambiente ou .env) e vai no cabeçalho, nunca na URL.
Usa só a biblioteca padrão. Execução: python spikes/itad_history.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API_URL = "https://api.isthereanydeal.com"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
USER_AGENT = "vale-esperar-spike/0.1"
TIMEOUT_SECONDS = 30

STEAM_SHOP_ID = 61
COUNTRIES = ("BR", "US")

# O padrão da API são só 3 meses; uma data antiga pede o histórico inteiro.
SINCE = "2000-01-01T00:00:00Z"

# Limite padrão do ITAD: 1000 req / 5 min.
SECONDS_BETWEEN_REQUESTS = 0.5

# Lançamentos de épocas diferentes, para ver o efeito na profundidade.
APP_IDS: dict[int, str] = {
    292030: "The Witcher 3",  # 2015
    413150: "Stardew Valley",  # 2016
    1091500: "Cyberpunk 2077",  # 2020
}


def load_api_key() -> str | None:
    """Lê a chave do ambiente ou, se não houver, do arquivo .env."""
    key = os.environ.get("ITAD_API_KEY")
    if key or not ENV_FILE.exists():
        return key
    for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "ITAD_API_KEY":
            return value.strip().strip("\"'") or None
    return None


def request_json(
    path: str,
    api_key: str | None = None,
    params: dict[str, Any] | None = None,
    body: Any = None,
) -> tuple[int, Any]:
    """Chama a API e devolve (status HTTP, JSON); erro HTTP traz o corpo do erro."""
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["ITAD-API-Key"] = api_key
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    request = urllib.request.Request(f"{API_URL}{path}{query}", data, headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")[:300]


def lookup_game_ids(app_ids: list[int], api_key: str | None) -> dict[int, str]:
    """Traduz appids da Steam para os IDs internos do ITAD."""
    shop_ids = [f"app/{app_id}" for app_id in app_ids]
    status, payload = request_json(
        f"/lookup/id/shop/{STEAM_SHOP_ID}/v1", api_key, body=shop_ids
    )
    print(f"Lookup: HTTP {status}\n{json.dumps(payload, indent=2)}")
    if status != 200:
        return {}
    found = {app_id: payload.get(f"app/{app_id}") for app_id in app_ids}
    return {app_id: game_id for app_id, game_id in found.items() if game_id}


def fetch_history(game_id: str, country: str, api_key: str) -> tuple[int, Any]:
    """Busca o log de mudanças de preço do jogo na Steam."""
    return request_json(
        "/games/history/v2",
        api_key,
        params={
            "id": game_id,
            "country": country,
            "shops": STEAM_SHOP_ID,
            "since": SINCE,
        },
    )


def describe_history(entries: list[dict[str, Any]]) -> str:
    """Resume profundidade, moeda e promoções de um histórico."""
    timestamps = sorted(entry["timestamp"] for entry in entries)
    deals = [entry["deal"] for entry in entries if entry.get("deal")]
    currencies = sorted({deal["price"]["currency"] for deal in deals})
    on_sale = sum(1 for deal in deals if deal.get("cut"))
    without_deal = len(entries) - len(deals)
    if not timestamps:
        return "0 registros"
    return (
        f"{len(entries)} registros, de {timestamps[0]} a {timestamps[-1]}, "
        f"moedas={currencies}, com_desconto={on_sale}, sem_deal={without_deal}"
    )


def main() -> int:
    """Traduz os appids e resume o histórico por jogo e país."""
    api_key = load_api_key()
    game_ids = lookup_game_ids(list(APP_IDS), api_key)

    if not api_key:
        print("\nITAD_API_KEY ausente: histórico não consultado.")
        return 2

    first_sample_shown = False
    for app_id, game_id in game_ids.items():
        print(f"\n--- {APP_IDS[app_id]} ({app_id})")
        for country in COUNTRIES:
            time.sleep(SECONDS_BETWEEN_REQUESTS)
            status, payload = fetch_history(game_id, country, api_key)
            if status != 200:
                print(f"{country}: HTTP {status}: {payload}")
                continue

            print(f"{country}: HTTP {status}, {describe_history(payload)}")
            if country == "BR" and payload and not first_sample_shown:
                print(json.dumps(payload[:2], indent=2, ensure_ascii=False))
                first_sample_shown = True

    return 0


if __name__ == "__main__":
    sys.exit(main())
