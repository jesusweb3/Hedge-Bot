from __future__ import annotations

import asyncio
import os
import uuid

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pybit.unified_trading import HTTP


def _str_to_bool(v: Optional[str]) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(slots=True)
class SymbolFilters:
    qty_step: float
    min_qty: float
    max_qty: float
    tick_size: float


class BybitClient:
    """Асинхронный обёртка над REST-интерфейсом pybit."""

    def __init__(self) -> None:
        load_dotenv()
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        if not api_key or not api_secret:
            raise RuntimeError("Не найдены ключи BYBIT_API_KEY/BYBIT_API_SECRET в .env")
        testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))
        self._http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                           timeout=10_000, recv_window=5_000)
        self._lock = asyncio.Lock()

    async def _call(self, func, *args, **kwargs):
        async with self._lock:
            return await asyncio.to_thread(func, *args, **kwargs)

    # ------------------------------------------------------------------
    # Общие проверки и данные
    # ------------------------------------------------------------------
    async def ensure_symbol_trading(self, symbol: str) -> Tuple[bool, str]:
        return await self._call(self._check_symbol_status, symbol)

    async def ensure_hedge_mode(self, symbol: str) -> None:
        enabled = await self._call(self._check_hedge_mode, symbol)
        if not enabled:
            await self._call(self._enable_hedge_mode, symbol)

    async def get_symbol_filters(self, symbol: str) -> SymbolFilters:
        return await self._call(self._get_symbol_filters, symbol)

    async def get_open_orders(self, symbol: str) -> List[dict]:
        return await self._call(self._get_open_orders, symbol)

    async def get_order_info(self, symbol: str, order_id: str) -> Optional[dict]:
        return await self._call(self._get_order_info, symbol, order_id)

    async def get_positions(self, symbol: str) -> List[dict]:
        return await self._call(self._get_positions, symbol)

    async def get_position_side(self, symbol: str, side: str) -> Optional[dict]:
        return await self._call(self._get_position_side, symbol, side)

    # ------------------------------------------------------------------
    # Управление ордерами
    # ------------------------------------------------------------------
    async def place_conditional_market_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        trigger_price: str,
        trigger_direction: int,
        trigger_by: str = "LastPrice",
        position_idx: Optional[int] = None,
        reduce_only: bool = False,
        close_on_trigger: bool = False,
        order_link_id: Optional[str] = None,
    ) -> str:
        return await self._call(
            self._place_conditional_market_order,
            symbol,
            side,
            qty,
            trigger_price,
            trigger_direction,
            trigger_by,
            position_idx,
            reduce_only,
            close_on_trigger,
            order_link_id,
        )

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        price: str,
        position_idx: Optional[int] = None,
        time_in_force: str = "GTC",
        reduce_only: bool = True,
        order_link_id: Optional[str] = None,
    ) -> str:
        return await self._call(
            self._place_limit_order,
            symbol,
            side,
            qty,
            price,
            position_idx,
            time_in_force,
            reduce_only,
            order_link_id,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> None:
        await self._call(self._cancel_order, symbol, order_id)

    async def cancel_all_orders(self, symbol: str) -> None:
        await self._call(self._cancel_all_orders, symbol)

    async def close_position_market(self, symbol: str, side: str) -> Optional[str]:
        return await self._call(self._close_position_market, symbol, side)

    # ------------------------------------------------------------------
    # Реализация синхронных методов
    # ------------------------------------------------------------------
    def _check_symbol_status(self, symbol: str) -> Tuple[bool, str]:
        resp = self._http.get_instruments_info(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        instruments = resp["result"].get("list") or []
        if not instruments:
            return False, "NotFound"
        status = instruments[0].get("status", "Unknown")
        return status == "Trading", status

    def _get_symbol_filters(self, symbol: str) -> SymbolFilters:
        resp = self._http.get_instruments_info(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        instruments = resp["result"].get("list") or []
        if not instruments:
            raise RuntimeError("Символ не найден")
        inst = instruments[0]
        lot = inst.get("lotSizeFilter", {})
        price = inst.get("priceFilter", {})
        return SymbolFilters(
            qty_step=float(lot.get("qtyStep", "0.0")),
            min_qty=float(lot.get("minOrderQty", "0.0")),
            max_qty=float(lot.get("maxOrderQty", "0.0")),
            tick_size=float(price.get("tickSize", "0.0")),
        )

    def _check_hedge_mode(self, symbol: str) -> bool:
        resp = self._http.get_positions(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        items = resp["result"].get("list") or []
        idxs = {int(i.get("positionIdx", 0)) for i in items}
        return 1 in idxs and 2 in idxs

    def _enable_hedge_mode(self, symbol: str) -> None:
        resp = self._http.switch_position_mode(category="linear", symbol=symbol, mode=3)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Не удалось включить хедж-режим: {resp}")

    def _get_open_orders(self, symbol: str) -> List[dict]:
        resp = self._http.get_open_orders(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        return resp["result"].get("list") or []

    def _get_order_info(self, symbol: str, order_id: str) -> Optional[dict]:
        # direct lookup
        resp = self._http.get_open_orders(category="linear", symbol=symbol, orderId=order_id)
        if isinstance(resp, dict) and resp.get("retCode") == 0:
            items = resp.get("result", {}).get("list") or []
            if items:
                return items[0]
        # search open orders list
        resp_open = self._http.get_open_orders(category="linear", symbol=symbol)
        if isinstance(resp_open, dict) and resp_open.get("retCode") == 0:
            for o in resp_open.get("result", {}).get("list") or []:
                if o.get("orderId") == order_id:
                    return o
        # lookup history
        cursor = None
        pages = 0
        while pages < 6:
            kwargs: Dict[str, Any] = {"category": "linear", "symbol": symbol}
            if cursor:
                kwargs["cursor"] = cursor
            kwargs["orderId"] = order_id
            resp_hist = self._http.get_order_history(**kwargs)
            if not isinstance(resp_hist, dict) or resp_hist.get("retCode") != 0:
                raise RuntimeError(f"Bybit API error: {resp_hist}")
            items = resp_hist.get("result", {}).get("list") or []
            for o in items:
                if o.get("orderId") == order_id:
                    return o
            cursor = resp_hist.get("result", {}).get("nextPageCursor")
            if not cursor:
                break
            pages += 1
        return None

    def _get_positions(self, symbol: str) -> List[dict]:
        resp = self._http.get_positions(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        items = resp["result"].get("list") or []
        return [p for p in items if float(p.get("size", "0") or 0) != 0]

    def _get_position_side(self, symbol: str, side: str) -> Optional[dict]:
        resp = self._http.get_positions(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        items = resp["result"].get("list") or []
        side = side.lower().strip()
        idx_map = {"long": 1, "short": 2}
        idx = idx_map.get(side)
        if idx is None:
            raise ValueError("Сторона должна быть 'long' или 'short'")
        for p in items:
            if int(p.get("positionIdx", 0)) == idx:
                if float(p.get("size", "0") or 0) != 0:
                    return p
                return None
        return None

    def _place_conditional_market_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        trigger_price: str,
        trigger_direction: int,
        trigger_by: str,
        position_idx: Optional[int],
        reduce_only: bool,
        close_on_trigger: bool,
        order_link_id: Optional[str],
    ) -> str:
        params: Dict[str, Any] = dict(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=qty,
            triggerPrice=trigger_price,
            triggerDirection=trigger_direction,
            triggerBy=trigger_by,
            stopOrderType="Stop",
            timeInForce="IOC",
            reduceOnly=reduce_only,
            closeOnTrigger=close_on_trigger,
            orderLinkId=order_link_id or f"cond-{uuid.uuid4().hex[:10]}",
        )
        if position_idx is not None:
            params["positionIdx"] = position_idx
        resp = self._http.place_order(**params)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        return resp["result"]["orderId"]

    def _place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        price: str,
        position_idx: Optional[int],
        time_in_force: str,
        reduce_only: bool,
        order_link_id: Optional[str],
    ) -> str:
        params: Dict[str, Any] = dict(
            category="linear",
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=qty,
            price=price,
            timeInForce=time_in_force,
            reduceOnly=reduce_only,
            orderLinkId=order_link_id or f"limit-{uuid.uuid4().hex[:10]}",
        )
        if position_idx is not None:
            params["positionIdx"] = position_idx
        resp = self._http.place_order(**params)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        return resp["result"]["orderId"]

    def _cancel_order(self, symbol: str, order_id: str) -> None:
        resp = self._http.cancel_order(category="linear", symbol=symbol, orderId=order_id)
        if not isinstance(resp, dict) or resp.get("retCode") not in (0, 110001):
            raise RuntimeError(f"Bybit API error: {resp}")

    def _cancel_all_orders(self, symbol: str) -> None:
        resp = self._http.cancel_all_orders(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") not in (0, 110001):
            raise RuntimeError(f"Bybit API error: {resp}")

    def _close_position_market(self, symbol: str, side: str) -> Optional[str]:
        resp = self._http.get_positions(category="linear", symbol=symbol)
        if not isinstance(resp, dict) or resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        items = resp["result"].get("list") or []
        target = None
        for p in items:
            if float(p.get("size", "0") or 0) == 0:
                continue
            p_side = (p.get("side") or "").lower()
            if side.lower() == "long" and p_side == "buy":
                target = p
                break
            if side.lower() == "short" and p_side == "sell":
                target = p
                break
        if not target:
            return None
        qty = target.get("size")
        pos_idx = int(target.get("positionIdx", 0))
        order_side = "Sell" if side.lower() == "long" else "Buy"
        params: Dict[str, Any] = dict(
            category="linear",
            symbol=symbol,
            side=order_side,
            orderType="Market",
            qty=qty,
            timeInForce="IOC",
            reduceOnly=True,
            orderLinkId=f"close-{uuid.uuid4().hex[:10]}",
        )
        if pos_idx in (1, 2):
            params["positionIdx"] = pos_idx
        resp_order = self._http.place_order(**params)
        if not isinstance(resp_order, dict) or resp_order.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp_order}")
        return resp_order["result"]["orderId"]
