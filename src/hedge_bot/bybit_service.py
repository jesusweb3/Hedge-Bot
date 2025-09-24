"""Service helpers built around the Bybit HTTP API."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Iterable, Optional

from dotenv import load_dotenv
from pybit.unified_trading import HTTP

from src.bybit.check_symbol_status import check_symbol_status
from src.bybit.check_hedge_mode import check_hedge_mode
from src.bybit.enable_hedge_mode_for_symbol import enable_hedge_mode_for_symbol


class BybitCredentialsError(RuntimeError):
    """Raised when API credentials are missing."""


@dataclass(slots=True)
class SymbolFilters:
    qty_step: Decimal
    min_qty: Decimal
    max_qty: Decimal
    tick_size: Decimal


class BybitService:
    """Encapsulates Bybit HTTP API interactions required by the bot."""

    def __init__(self) -> None:
        load_dotenv()
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        testnet = self._str_to_bool(os.getenv("BYBIT_TESTNET"))
        if not api_key or not api_secret:
            raise BybitCredentialsError(
                "Environment variables BYBIT_API_KEY and BYBIT_API_SECRET must be provided"
            )
        self._http = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            timeout=10_000,
            recv_window=5_000,
        )
        self._filters_cache: Dict[str, SymbolFilters] = {}

    @staticmethod
    def _str_to_bool(value: Optional[str]) -> bool:
        return (value or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    def ensure_symbol_trading(self, symbol: str) -> None:
        ok, status = check_symbol_status(symbol)
        if not ok:
            raise RuntimeError(f"Symbol {symbol} is not tradable: {status}")

    def ensure_hedge_mode(self, symbol: str) -> None:
        if not check_hedge_mode(symbol):
            enable_hedge_mode_for_symbol(symbol)
            time.sleep(0.5)
            if not check_hedge_mode(symbol):
                raise RuntimeError("Failed to enable hedge mode for symbol")

    def _fetch_filters(self, symbol: str) -> SymbolFilters:
        if symbol in self._filters_cache:
            return self._filters_cache[symbol]
        resp = self._http.get_instruments_info(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error while fetching filters: {resp}")
        instruments = resp.get("result", {}).get("list") or []
        if not instruments:
            raise RuntimeError(f"No instrument information for {symbol}")
        inst = instruments[0]
        lot = inst.get("lotSizeFilter", {})
        price = inst.get("priceFilter", {})
        filters = SymbolFilters(
            qty_step=Decimal(lot.get("qtyStep")),
            min_qty=Decimal(lot.get("minOrderQty")),
            max_qty=Decimal(lot.get("maxOrderQty")),
            tick_size=Decimal(price.get("tickSize")),
        )
        self._filters_cache[symbol] = filters
        return filters

    def get_last_price(self, symbol: str) -> Decimal:
        resp = self._http.get_tickers(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error while fetching price: {resp}")
        tickers = resp.get("result", {}).get("list") or []
        if not tickers:
            raise RuntimeError(f"No ticker information for {symbol}")
        return Decimal(tickers[0]["lastPrice"])

    def quantise_qty(self, symbol: str, qty: Decimal) -> Decimal:
        filters = self._fetch_filters(symbol)
        step = filters.qty_step
        quantised = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
        if quantised < filters.min_qty:
            raise RuntimeError(
                f"Quantity {quantised} is below minimum {filters.min_qty} for {symbol}"
            )
        return quantised

    def quantise_price(self, symbol: str, price: Decimal) -> Decimal:
        tick = self._fetch_filters(symbol).tick_size
        return (price / tick).to_integral_value(rounding=ROUND_DOWN) * tick

    def place_conditional_market_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        trigger_price: Decimal,
        trigger_direction: int,
        trigger_by: str,
        position_idx: int,
        reduce_only: bool = False,
        close_on_trigger: bool = False,
    ) -> str:
        resp = self._http.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            triggerPrice=str(trigger_price),
            triggerDirection=trigger_direction,
            triggerBy=trigger_by,
            positionIdx=position_idx,
            reduceOnly=reduce_only,
            closeOnTrigger=close_on_trigger,
            stopOrderType="Stop",
            timeInForce="IOC",
        )
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Failed to place conditional order: {resp}")
        return resp["result"]["orderId"]

    def place_stop_market(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        trigger_price: Decimal,
        trigger_direction: int,
        trigger_by: str,
        position_idx: int,
    ) -> str:
        return self.place_conditional_market_order(
            symbol=symbol,
            side=side,
            qty=qty,
            trigger_price=trigger_price,
            trigger_direction=trigger_direction,
            trigger_by=trigger_by,
            position_idx=position_idx,
            reduce_only=True,
            close_on_trigger=True,
        )

    def place_limit_reduce_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        position_idx: int,
    ) -> str:
        resp = self._http.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=str(qty),
            price=str(price),
            timeInForce="GTC",
            reduceOnly=True,
            positionIdx=position_idx,
        )
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Failed to place limit order: {resp}")
        return resp["result"]["orderId"]

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        position_idx: int,
        reduce_only: bool = False,
    ) -> str:
        resp = self._http.place_order(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=str(qty),
            price=str(price),
            timeInForce="GTC",
            reduceOnly=reduce_only,
            positionIdx=position_idx,
        )
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Failed to place limit order: {resp}")
        return resp["result"]["orderId"]

    def cancel_order(self, symbol: str, order_id: str) -> None:
        resp = self._http.cancel_order(category="linear", symbol=symbol, orderId=order_id)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Failed to cancel order {order_id}: {resp}")

    def cancel_all_orders(self, symbol: str) -> None:
        resp = self._http.cancel_all_orders(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Failed to cancel all orders: {resp}")

    def close_position_market(self, symbol: str, position_side: str) -> Optional[str]:
        from src.bybit.close_position_market import close_position_market

        return close_position_market(symbol, position_side)

    def get_order_info(self, symbol: str, order_id: str) -> Optional[dict]:
        resp = self._http.get_open_orders(category="linear", symbol=symbol, orderId=order_id)
        if isinstance(resp, dict) and resp.get("retCode") == 0:
            items = resp.get("result", {}).get("list") or []
            if items:
                return items[0]
        resp_hist = self._http.get_order_history(category="linear", symbol=symbol, orderId=order_id)
        if isinstance(resp_hist, dict) and resp_hist.get("retCode") == 0:
            items = resp_hist.get("result", {}).get("list") or []
            if items:
                return items[0]
        return None

    def get_open_orders(self, symbol: str) -> Iterable[dict]:
        resp = self._http.get_open_orders(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Failed to fetch open orders: {resp}")
        return resp.get("result", {}).get("list") or []

    def get_positions(self, symbol: str) -> Iterable[dict]:
        resp = self._http.get_positions(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Failed to fetch positions: {resp}")
        return resp.get("result", {}).get("list") or []

    def convert_usdt_to_qty(self, symbol: str, amount_usdt: Decimal, price: Decimal) -> Decimal:
        qty = (amount_usdt / price).quantize(Decimal("0.00000001"))
        return self.quantise_qty(symbol, qty)
