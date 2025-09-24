# -*- coding: utf-8 -*-
"""
Модуль: health-check (ping) Bybit API.
Запрашивает /v5/market/time и выводит "OK <latency_ms>ms" при успешном ответе.
"""

import os
import sys
import time
from dotenv import load_dotenv
from pybit.unified_trading import HTTP


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def get_ping_server() -> float:
    """
    Делает запрос к Bybit /market/time, возвращает латентность (мс).
    Исключение при ошибке.
    """
    load_dotenv()
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    http = HTTP(testnet=testnet, timeout=10_000, recv_window=5_000)

    t0 = time.perf_counter()
    resp = http.get_server_time()
    t1 = time.perf_counter()

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    latency_ms = round((t1 - t0) * 1000, 2)
    return latency_ms


if __name__ == "__main__":
    try:
        latency = get_ping_server()
        print(f"OK {latency}ms")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
