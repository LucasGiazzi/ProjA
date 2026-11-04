"""Spike da Fase 0: wishlist e biblioteca do perfil do autor.

Tarefa 5: consulta IWishlistService/GetWishlist/v1 e
IPlayerService/GetOwnedGames/v1 e registra o formato das respostas.
STEAM_API_KEY e STEAM_ID vêm do ambiente ou do .env. Nenhum dos dois é impresso.
Usa só a biblioteca padrão. Execução: python spikes/steam_profile.py
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

API_URL = "https://api.steampowered.com"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
USER_AGENT = "vale-esperar-spike/0.1"
TIMEOUT_SECONDS = 30
SECONDS_BETWEEN_REQUESTS = 1.5
STEAM_ID_LENGTH = 17


def read_env(name: str) -> str | None:
    """Lê uma variável do ambiente ou, se não houver, do arquivo .env."""
    value = os.environ.get(name)
    if value or not ENV_FILE.exists():
        return value
    for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        key, _, raw_value = line.partition("=")
        if key.strip() == name:
            return raw_value.strip().strip("\"'") or None
    return None


def get_json(
    path: str, params: dict[str, Any], api_key: str | None = None
) -> tuple[int, Any]:
    """Faz um GET; a chave vai no cabeçalho para não aparecer em URLs."""
    headers = {"User-Agent": USER_AGENT}
    if api_key:
        headers["x-webapi-key"] = api_key
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{API_URL}{path}?{query}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        # Só o status: o corpo do erro não é necessário e pode ecoar a requisição.
        return error.code, None


def fetch_wishlist(steam_id: str) -> list[dict[str, Any]]:
    """Busca a wishlist; requer perfil público, sem chave."""
    status, payload = get_json(
        "/IWishlistService/GetWishlist/v1/", {"steamid": steam_id}
    )
    response = (payload or {}).get("response", {})
    print(f"Wishlist: HTTP {status}, chaves={sorted(response)}")
    return response.get("items", [])


def fetch_owned_games(steam_id: str, api_key: str) -> list[dict[str, Any]]:
    """Busca a biblioteca, incluindo nomes e jogos gratuitos já jogados."""
    status, payload = get_json(
        "/IPlayerService/GetOwnedGames/v1/",
        {
            "steamid": steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
        },
        api_key,
    )
    response = (payload or {}).get("response", {})
    print(f"Biblioteca: HTTP {status}, chaves={sorted(response)}")
    return response.get("games", [])


def main() -> int:
    """Consulta wishlist e biblioteca e cruza as duas listas."""
    api_key = read_env("STEAM_API_KEY")
    steam_id = read_env("STEAM_ID")

    if not api_key or not steam_id:
        print(
            f"Faltam variáveis: STEAM_API_KEY presente={bool(api_key)}, "
            f"STEAM_ID presente={bool(steam_id)}"
        )
        return 2
    if len(steam_id) != STEAM_ID_LENGTH or not steam_id.isdigit():
        print(f"STEAM_ID deve ter {STEAM_ID_LENGTH} dígitos.")
        return 2

    wishlist = fetch_wishlist(steam_id)
    print(f"{len(wishlist)} jogos na wishlist")
    print(json.dumps(wishlist[:2], indent=2, ensure_ascii=False))

    time.sleep(SECONDS_BETWEEN_REQUESTS)
    owned = fetch_owned_games(steam_id, api_key)
    print(f"{len(owned)} jogos na biblioteca")
    print(json.dumps(owned[:1], indent=2, ensure_ascii=False))

    overlap = {item["appid"] for item in wishlist} & {
        game["appid"] for game in owned
    }
    print(f"Na wishlist e já na biblioteca: {len(overlap)}")

    return 0 if wishlist and owned else 1


if __name__ == "__main__":
    sys.exit(main())
