"""Leitura de configuração e segredos a partir do ambiente."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_local_env(path: Path = ENV_FILE) -> None:
    """Carrega o .env local, se existir, sem sobrescrever o ambiente."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def require_env(name: str) -> str:
    """Devolve uma variável obrigatória; a mensagem de erro nunca traz o valor."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente ausente: {name}")
    return value
