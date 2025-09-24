# -*- coding: utf-8 -*-
"""
Модуль: получение списка линейных БЕССРОЧНЫХ фьючерсов USDT (Bybit V5).
Использует pybit==5.11.0, читает BYBIT_TESTNET из .env.
При запуске модуля печатает список символов (один в строке).
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def get_perpetual_usdt_symbols() -> list[str]:
    """
    Возвращает список символов линейных БЕССРОЧНЫХ фьючерсов USDT.
    """
    load_dotenv()
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    http = HTTP(testnet=testnet, timeout=10_000, recv_window=5_000)

    resp = http.get_instruments_info(category="linear")

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    try:
        instruments = resp["result"]["list"]
        # оставляем только USDT-пары с контрактом типа LinearPerpetual
        symbols = [
            inst["symbol"]
            for inst in instruments
            if inst.get("quoteCoin") == "USDT"
            and inst.get("contractType") == "LinearPerpetual"
        ]
        return symbols
    except Exception as e:
        raise RuntimeError(f"Не удалось разобрать ответ Bybit: {resp}") from e


if __name__ == "__main__":
    try:
        syms = get_perpetual_usdt_symbols()
        for s in syms:
            print(s)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
