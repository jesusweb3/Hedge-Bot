# -*- coding: utf-8 -*-
"""
Модуль: получение баланса USDT (Unified/Futures) на Bybit (V5) с использованием pybit==5.11.0.
Читает ключи и флаг тестнета из .env в корне проекта.
При запуске модуля печатает числовой баланс USDT (округлённый до 2 знаков).
"""

from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import os
import sys

from dotenv import load_dotenv
from pybit.unified_trading import HTTP


def _str_to_bool(v: str | None) -> bool:
    if v is None:
        return False
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_futures_usdt_balance() -> float:
    """
    Возвращает баланс USDT (Unified/Futures), округлённый до 2 знаков.
    """
    load_dotenv()

    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Отсутствуют BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(
        testnet=testnet,
        api_key=api_key,
        api_secret=api_secret,
        timeout=10_000,
        recv_window=5_000,
    )

    # Запрашиваем баланс Unified-аккаунта по USDT
    resp = http.get_wallet_balance(accountType="UNIFIED", coin="USDT")

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    try:
        coins = resp["result"]["list"][0]["coin"]
        usdt_entry = next(c for c in coins if c.get("coin") == "USDT")
        wallet_balance_str = usdt_entry["walletBalance"]
    except StopIteration:
        raise RuntimeError("USDT не найден в ответе Bybit")
    except Exception as e:
        raise RuntimeError(f"Не удалось разобрать ответ Bybit: {resp}") from e

    # Округляем до двух знаков
    balance = Decimal(wallet_balance_str).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(balance)


if __name__ == "__main__":
    try:
        value = get_futures_usdt_balance()
        print(value)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
