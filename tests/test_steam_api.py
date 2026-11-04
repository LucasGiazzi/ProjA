"""Testes das regras de lote do cliente da Steam, sem acesso à rede."""

from typing import Any

import pytest

from ingestion import steam_api

GOOD_ENTRY = {"success": True, "data": {"price_overview": {"final": 100}}}


def fake_get_json(fail_when: Any, status: int = 500) -> Any:
    """Cria um get_json falso que falha para os lotes indicados."""

    def fake(_url: str, params: dict[str, Any]) -> tuple[int, Any]:
        app_ids = [int(value) for value in params["appids"].split(",")]
        if fail_when(app_ids):
            return status, None
        return 200, {str(app_id): GOOD_ENTRY for app_id in app_ids}

    return fake


def test_chunked_respects_size() -> None:
    assert steam_api.chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_failed_batch_is_split_and_recovers_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reproduz o caso real: o lote grande falha, os menores passam.
    monkeypatch.setattr(
        steam_api, "get_json", fake_get_json(lambda ids: len(ids) > 2)
    )

    entries, failed = steam_api.fetch_price_batch([1, 2, 3, 4, 5])

    assert sorted(entries) == ["1", "2", "3", "4", "5"]
    assert failed == {}


def test_bad_game_does_not_take_down_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(steam_api, "get_json", fake_get_json(lambda ids: 3 in ids))

    entries, failed = steam_api.fetch_price_batch([1, 2, 3, 4])

    assert sorted(entries) == ["1", "2", "4"]
    assert failed == {3: 500}


def test_rate_limit_does_not_split_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[int]] = []
    fake = fake_get_json(lambda ids: calls.append(ids) or True, status=429)
    monkeypatch.setattr(steam_api, "get_json", fake)

    entries, failed = steam_api.fetch_price_batch([1, 2, 3, 4])

    assert entries == {}
    assert failed == {1: 429, 2: 429, 3: 429, 4: 429}
    assert len(calls) == 1


def test_null_body_counts_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(steam_api, "get_json", lambda *_: (200, None))

    entries, failed = steam_api.fetch_price_batch([1])

    assert entries == {}
    assert failed == {1: 200}


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (GOOD_ENTRY, True),
        ({"success": True, "data": []}, False),
        ({"success": False}, False),
        (None, False),
    ],
)
def test_has_price(entry: dict[str, Any] | None, expected: bool) -> None:
    assert steam_api.has_price(entry) is expected
