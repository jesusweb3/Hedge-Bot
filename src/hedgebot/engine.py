from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Optional

from .bybit_client import BybitClient, SymbolFilters
from .config import InstrumentSettings
from .events import LogEvent, OrdersEvent, StatusEvent
from .state import InstrumentStatus, ManagedOrder, OrderKind
from .utils import clamp_to_step_str, ensure_minimum


class InstrumentEngine:
    """Управляет логикой торговли по одному инструменту."""

    def __init__(self, settings: InstrumentSettings, client: BybitClient) -> None:
        self.settings = settings.clone()
        self.client = client
        self.status: InstrumentStatus = InstrumentStatus.CONFIGURED
        self.events: asyncio.Queue = asyncio.Queue()

        self._orders: Dict[str, ManagedOrder] = {}
        self._symbol_filters: Optional[SymbolFilters] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._protection_deployed = False
        self._entry_prices: Dict[str, float] = {"long": 0.0, "short": 0.0}
        self._base_qty_side: Dict[str, float] = {"long": self.settings.base_quantity, "short": self.settings.base_quantity}
        self._finalized = False

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------
    async def update_settings(self, settings: InstrumentSettings) -> None:
        if self.status in {InstrumentStatus.WAITING_ENTRY, InstrumentStatus.ACTIVE}:
            raise RuntimeError("Нельзя менять настройки во время работы")
        self.settings = settings.clone()
        self.settings.validate()
        await self._emit_status(InstrumentStatus.CONFIGURED, "Настройки обновлены")

    async def start(self) -> None:
        if self.status in {InstrumentStatus.WAITING_ENTRY, InstrumentStatus.ACTIVE}:
            raise RuntimeError("Инструмент уже запущен")
        self.settings.validate()
        ok, reason = await self.client.ensure_symbol_trading(self.settings.symbol)
        if not ok:
            raise RuntimeError(f"Символ {self.settings.symbol} недоступен для торговли ({reason})")
        await self.client.ensure_hedge_mode(self.settings.symbol)
        self._symbol_filters = await self.client.get_symbol_filters(self.settings.symbol)

        self._orders.clear()
        self._protection_deployed = False
        self._stop_event = asyncio.Event()
        self._finalized = False

        await self._emit_status(InstrumentStatus.WAITING_ENTRY, "Выставление условных ордеров входа")
        await self._place_entry_orders()
        await self._emit_orders_event()

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._poll_task:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        await self.client.cancel_all_orders(self.settings.symbol)
        await self._emit_orders_event()
        await self._emit_status(InstrumentStatus.STOPPED, "Остановлено пользователем")

    async def close_all(self) -> None:
        self._stop_event.set()
        if self._poll_task:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        await self.client.cancel_all_orders(self.settings.symbol)
        await self.client.close_position_market(self.settings.symbol, "long")
        await self.client.close_position_market(self.settings.symbol, "short")
        await self._emit_orders_event()
        await self._emit_status(InstrumentStatus.COMPLETED, "Позиция закрыта вручную")

    # ------------------------------------------------------------------
    # Основной цикл мониторинга
    # ------------------------------------------------------------------
    async def _poll_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await self._poll_once()
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pylint: disable=broad-except
            await self._handle_error(exc)

    async def _poll_once(self) -> None:
        symbol = self.settings.symbol
        open_orders = await self.client.get_open_orders(symbol)
        open_map = {o.get("orderId"): o for o in open_orders if o.get("orderId")}

        for order in list(self._orders.values()):
            prev_status = order.status
            data = open_map.get(order.order_id)
            status = prev_status
            if data:
                status = self._extract_status(data) or prev_status
            else:
                data = await self.client.get_order_info(symbol, order.order_id)
                if data:
                    status = self._extract_status(data) or prev_status
            if status != prev_status:
                order.mark_status(status)
                self._update_order_from_data(order, data)
                await self._handle_order_status_change(order, status, data)

        await self._emit_orders_event()

    # ------------------------------------------------------------------
    # Размещение ордеров
    # ------------------------------------------------------------------
    async def _place_entry_orders(self) -> None:
        filters = self._require_filters()
        qty_str = self._format_qty(self.settings.base_quantity, filters)
        trigger_price = self._format_price(self.settings.entry_trigger_price, filters)

        order_long_id = await self.client.place_conditional_market_order(
            symbol=self.settings.symbol,
            side="Buy",
            qty=qty_str,
            trigger_price=trigger_price,
            trigger_direction=self.settings.entry_trigger_direction,
            trigger_by=self.settings.trigger_by,
            position_idx=1,
            reduce_only=False,
            close_on_trigger=False,
        )
        self._orders[order_long_id] = ManagedOrder(
            order_id=order_long_id,
            symbol=self.settings.symbol,
            side="Buy",
            position_side="long",
            kind=OrderKind.ENTRY,
            quantity=float(Decimal(qty_str)),
            trigger_price=float(trigger_price),
            reduce_only=False,
        )
        await self._log(f"Условный ордер на вход LONG выставлен ({order_long_id})")

        order_short_id = await self.client.place_conditional_market_order(
            symbol=self.settings.symbol,
            side="Sell",
            qty=qty_str,
            trigger_price=trigger_price,
            trigger_direction=3 - self.settings.entry_trigger_direction,
            trigger_by=self.settings.trigger_by,
            position_idx=2,
            reduce_only=False,
            close_on_trigger=False,
        )
        self._orders[order_short_id] = ManagedOrder(
            order_id=order_short_id,
            symbol=self.settings.symbol,
            side="Sell",
            position_side="short",
            kind=OrderKind.ENTRY,
            quantity=float(Decimal(qty_str)),
            trigger_price=float(trigger_price),
            reduce_only=False,
        )
        await self._log(f"Условный ордер на вход SHORT выставлен ({order_short_id})")

    async def _deploy_protection_orders(self) -> None:
        if self._protection_deployed:
            return
        filters = self._require_filters()

        for side in ("long", "short"):
            entry_price = self._entry_prices.get(side)
            if not entry_price:
                position = await self.client.get_position_side(self.settings.symbol, side)
                if position:
                    entry_price = float(position.get("avgPrice") or position.get("entryPrice") or 0)
                    self._entry_prices[side] = entry_price
            if not entry_price or entry_price <= 0:
                raise RuntimeError(f"Не удалось определить цену входа для {side}")

            base_qty = self._base_qty_side.get(side, self.settings.base_quantity)
            await self._create_take_profits(side, entry_price, base_qty, filters)
            await self._create_stop_losses(side, entry_price, base_qty, filters)

        self._protection_deployed = True
        await self._emit_status(InstrumentStatus.ACTIVE, "Позиции открыты, ордера защиты выставлены")

    async def _create_take_profits(
        self,
        side: str,
        entry_price: float,
        base_qty: float,
        filters: SymbolFilters,
    ) -> None:
        for idx, tp in enumerate(self.settings.take_profits, start=1):
            qty = base_qty * tp.quantity_percent / 100.0
            qty_str = self._format_qty(qty, filters)
            if side == "long":
                price = entry_price * (1 + tp.offset_percent / 100.0)
                order_side = "Sell"
                position_idx = 1
            else:
                price = entry_price * (1 - tp.offset_percent / 100.0)
                order_side = "Buy"
                position_idx = 2
            price_str = self._format_price(price, filters)
            order_id = await self.client.place_limit_order(
                symbol=self.settings.symbol,
                side=order_side,
                qty=qty_str,
                price=price_str,
                position_idx=position_idx,
                reduce_only=True,
            )
            kind = OrderKind.FINAL_TAKE_PROFIT if idx == len(self.settings.take_profits) else OrderKind.TAKE_PROFIT
            self._orders[order_id] = ManagedOrder(
                order_id=order_id,
                symbol=self.settings.symbol,
                side=order_side,
                position_side=side,
                kind=kind,
                quantity=float(Decimal(qty_str)),
                price=float(price_str),
                level=idx,
                reduce_only=True,
            )
            await self._log(f"TP{idx} для {side.upper()} выставлен по цене {price_str} ({order_id})")

    async def _create_stop_losses(
        self,
        side: str,
        entry_price: float,
        base_qty: float,
        filters: SymbolFilters,
    ) -> None:
        sorted_stops = self.settings.stop_losses_sorted
        for idx, sl in enumerate(sorted_stops, start=1):
            qty = base_qty * sl.quantity_percent / 100.0
            qty_str = self._format_qty(qty, filters)
            if side == "long":
                trigger_price = entry_price * (1 - sl.offset_percent / 100.0)
                order_side = "Sell"
                position_idx = 1
                trigger_direction = 2
            else:
                trigger_price = entry_price * (1 + sl.offset_percent / 100.0)
                order_side = "Buy"
                position_idx = 2
                trigger_direction = 1
            trigger_price_str = self._format_price(trigger_price, filters)
            order_id = await self.client.place_conditional_market_order(
                symbol=self.settings.symbol,
                side=order_side,
                qty=qty_str,
                trigger_price=trigger_price_str,
                trigger_direction=trigger_direction,
                trigger_by=self.settings.trigger_by,
                position_idx=position_idx,
                reduce_only=True,
                close_on_trigger=True,
            )
            self._orders[order_id] = ManagedOrder(
                order_id=order_id,
                symbol=self.settings.symbol,
                side=order_side,
                position_side=side,
                kind=OrderKind.STOP_LOSS,
                quantity=float(Decimal(qty_str)),
                trigger_price=float(trigger_price_str),
                level=idx,
                reduce_only=True,
            )
            await self._log(f"SL{idx} для {side.upper()} выставлен по цене {trigger_price_str} ({order_id})")

    # ------------------------------------------------------------------
    # Обработка статусов
    # ------------------------------------------------------------------
    async def _handle_order_status_change(self, order: ManagedOrder, status: str, data: Optional[dict]) -> None:
        if status == "Filled":
            await self._on_order_filled(order, data)
        elif status in {"Cancelled", "Rejected"}:
            await self._log(f"Ордер {order.order_id} отменён ({order.kind.value})", level="warning")
        elif status == "New":
            await self._log(f"Ордер {order.order_id} принят биржей", level="debug")

    async def _on_order_filled(self, order: ManagedOrder, data: Optional[dict]) -> None:
        qty = float(data.get("cumExecQty") or data.get("qty") or order.quantity) if data else order.quantity
        price = float(data.get("avgPrice") or data.get("triggerPrice") or data.get("price") or order.price or 0) if data else order.price or 0
        await self._log(f"Ордер {order.order_id} ({order.kind.value}) исполнен на {qty}")

        if order.kind == OrderKind.ENTRY:
            self._entry_prices[order.position_side] = price or self.settings.entry_trigger_price
            self._base_qty_side[order.position_side] = qty
            await self._check_activation_ready()
        elif order.kind == OrderKind.TAKE_PROFIT:
            await self._maybe_place_refill_after_tp(order.position_side, qty)
        elif order.kind == OrderKind.FINAL_TAKE_PROFIT:
            await self._finalize_trade(f"Финальный TP достигнут для {order.position_side.upper()}")
        elif order.kind == OrderKind.STOP_LOSS:
            await self._place_refill_after_stop(order.position_side, qty)
        elif order.kind == OrderKind.REFILL:
            await self._log(f"Доливка {order.position_side.upper()} выполнена на {qty}")

    async def _check_activation_ready(self) -> None:
        if all(self._entry_prices.get(side) for side in ("long", "short")) and not self._protection_deployed:
            await self._deploy_protection_orders()

    async def _maybe_place_refill_after_tp(self, side: str, qty: float) -> None:
        refill = self.settings.refill
        if not refill.enabled_after_tp1 or refill.quantity_percent <= 0:
            return
        base_qty = self._base_qty_side.get(side, self.settings.base_quantity)
        refill_qty = base_qty * refill.quantity_percent / 100.0
        refill_qty = min(refill_qty, qty)
        if refill_qty <= 0:
            return
        filters = self._require_filters()
        qty_str = self._format_qty(refill_qty, filters)
        entry_price = self._entry_prices.get(side) or self.settings.entry_trigger_price
        if side == "long":
            price = entry_price * (1 - refill.price_offset_percent / 100.0)
            order_side = "Buy"
            position_idx = 1
        else:
            price = entry_price * (1 + refill.price_offset_percent / 100.0)
            order_side = "Sell"
            position_idx = 2
        price_str = self._format_price(price, filters)
        order_id = await self.client.place_limit_order(
            symbol=self.settings.symbol,
            side=order_side,
            qty=qty_str,
            price=price_str,
            position_idx=position_idx,
            reduce_only=False,
        )
        self._orders[order_id] = ManagedOrder(
            order_id=order_id,
            symbol=self.settings.symbol,
            side=order_side,
            position_side=side,
            kind=OrderKind.REFILL,
            quantity=float(Decimal(qty_str)),
            price=float(price_str),
            reduce_only=False,
        )
        await self._log(f"После TP выставлена доливка {side.upper()} по цене {price_str} ({order_id})")

    async def _place_refill_after_stop(self, side: str, qty: float) -> None:
        if qty <= 0:
            return
        filters = self._require_filters()
        qty_str = self._format_qty(qty, filters)
        entry_price = self._entry_prices.get(side) or self.settings.entry_trigger_price
        price_str = self._format_price(entry_price, filters)
        if side == "long":
            order_side = "Buy"
            position_idx = 1
        else:
            order_side = "Sell"
            position_idx = 2
        order_id = await self.client.place_limit_order(
            symbol=self.settings.symbol,
            side=order_side,
            qty=qty_str,
            price=price_str,
            position_idx=position_idx,
            reduce_only=False,
        )
        self._orders[order_id] = ManagedOrder(
            order_id=order_id,
            symbol=self.settings.symbol,
            side=order_side,
            position_side=side,
            kind=OrderKind.REFILL,
            quantity=float(Decimal(qty_str)),
            price=float(price_str),
            reduce_only=False,
        )
        await self._log(f"После SL выставлена доливка {side.upper()} по цене {price_str} ({order_id})")

    async def _finalize_trade(self, reason: str) -> None:
        if self._finalized:
            return
        self._finalized = True
        await self.client.cancel_all_orders(self.settings.symbol)
        await self.client.close_position_market(self.settings.symbol, "long")
        await self.client.close_position_market(self.settings.symbol, "short")
        await self._emit_orders_event()
        await self._emit_status(InstrumentStatus.COMPLETED, reason)
        self._stop_event.set()
        if self._poll_task:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------
    def _require_filters(self) -> SymbolFilters:
        if not self._symbol_filters:
            raise RuntimeError("Не удалось получить биржевые фильтры")
        return self._symbol_filters

    def _format_qty(self, qty: float, filters: SymbolFilters) -> str:
        qty = ensure_minimum(qty, filters.min_qty)
        return clamp_to_step_str(qty, filters.qty_step, rounding=ROUND_DOWN)

    def _format_price(self, price: float, filters: SymbolFilters) -> str:
        return clamp_to_step_str(price, filters.tick_size, rounding=ROUND_HALF_UP)

    def _extract_status(self, data: Optional[dict]) -> Optional[str]:
        if not data:
            return None
        for key in ("orderStatus", "stopOrderStatus", "triggerStatus"):
            status = data.get(key)
            if status:
                return status
        return None

    def _update_order_from_data(self, order: ManagedOrder, data: Optional[dict]) -> None:
        if not data:
            return
        if data.get("price"):
            order.price = float(data["price"])
        if data.get("triggerPrice"):
            order.trigger_price = float(data["triggerPrice"])

    async def _emit_status(self, status: InstrumentStatus, details: Optional[str] = None) -> None:
        self.status = status
        await self.events.put(StatusEvent(self.settings.symbol, datetime.utcnow(), status, details))

    async def _emit_orders_event(self) -> None:
        await self.events.put(OrdersEvent(self.settings.symbol, datetime.utcnow(), list(self._orders.values())))

    async def _log(self, message: str, level: str = "info") -> None:
        await self.events.put(LogEvent(self.settings.symbol, datetime.utcnow(), level, message))

    async def _handle_error(self, exc: Exception) -> None:
        await self._log(f"Ошибка: {exc}", level="error")
        await self._emit_status(InstrumentStatus.ERROR, str(exc))
        self._stop_event.set()

