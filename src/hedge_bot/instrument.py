"""Orchestration logic for trading a single hedged instrument."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from .config import InstrumentConfig, SideConfig
from .state import InstrumentState, InstrumentStatus, OrderInfo, OrderType
from .bybit_service import BybitService


@dataclass(slots=True)
class EntryOrders:
    long_id: Optional[str] = None
    short_id: Optional[str] = None

    def completed(self) -> bool:
        return bool(self.long_id and self.short_id)


class HedgeInstrument:
    """Lifecycle manager for a hedged trading instrument."""

    def __init__(self, config: InstrumentConfig, service: BybitService) -> None:
        self.config = config
        self.service = service
        self.state = InstrumentState()
        self._entry_orders = EntryOrders()
        self._entry_qty: Decimal | None = None
        self._task: Optional[asyncio.Task[None]] = None
        self._running = asyncio.Event()
        self._poll_interval = 2.0

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        await self._prepare_symbol()
        self.state.log("Запуск стратегии")
        await self._place_entry_orders()
        self.state.status = InstrumentStatus.WAITING_ENTRY
        self._running.set()
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        self.state.log("Остановка стратегии по запросу пользователя")
        self._running.clear()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        try:
            self.service.cancel_all_orders(self.config.symbol)
        except Exception as exc:  # noqa: BLE001 - we log and continue
            self.state.log(f"Ошибка при отмене ордеров: {exc}")
        for side in ("long", "short"):
            try:
                closed = self.service.close_position_market(self.config.symbol, side)
                if closed:
                    self.state.log(f"Позиция {side} закрыта ордером {closed}")
            except Exception as exc:  # noqa: BLE001
                self.state.log(f"Ошибка при закрытии позиции {side}: {exc}")
        self.state.status = InstrumentStatus.STOPPED

    async def _prepare_symbol(self) -> None:
        self.service.ensure_symbol_trading(self.config.symbol)
        self.service.ensure_hedge_mode(self.config.symbol)

    async def _place_entry_orders(self) -> None:
        symbol = self.config.symbol
        entry_price = self.config.entry_trigger_price
        qty = self.service.convert_usdt_to_qty(symbol, self.config.entry_quantity_usdt, entry_price)
        self._entry_qty = qty

        long_order = self.service.place_conditional_market_order(
            symbol=symbol,
            side="Buy",
            qty=qty,
            trigger_price=entry_price,
            trigger_direction=2,  # <= trigger
            trigger_by=self.config.trigger_by,
            position_idx=1,
        )
        short_order = self.service.place_conditional_market_order(
            symbol=symbol,
            side="Sell",
            qty=qty,
            trigger_price=entry_price,
            trigger_direction=1,  # >= trigger
            trigger_by=self.config.trigger_by,
            position_idx=2,
        )
        self._entry_orders.long_id = long_order
        self._entry_orders.short_id = short_order
        self._register_order(
            order_id=long_order,
            order_type=OrderType.ENTRY_LONG,
            side="Buy",
            position_side="long",
            qty=float(qty),
            price=float(entry_price),
        )
        self._register_order(
            order_id=short_order,
            order_type=OrderType.ENTRY_SHORT,
            side="Sell",
            position_side="short",
            qty=float(qty),
            price=float(entry_price),
        )
        self.state.log(
            f"Выставлены входные ордера long={long_order} short={short_order} объём {qty}"
        )

    def _register_order(
        self,
        order_id: str,
        order_type: OrderType,
        side: str,
        position_side: str,
        qty: float,
        price: float | None,
        tag: str | None = None,
    ) -> None:
        info = OrderInfo(
            order_id=order_id,
            order_type=order_type,
            side=side,
            position_side=position_side,
            qty=qty,
            price=price,
            tag=tag,
        )
        self.state.add_order(info)

    async def _monitor_loop(self) -> None:
        try:
            while self._running.is_set():
                await self._check_orders()
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.state.last_error = str(exc)
            self.state.log(f"Ошибка мониторинга: {exc}")
            self.state.status = InstrumentStatus.ERROR

    async def _check_orders(self) -> None:
        symbol = self.config.symbol
        for order_id, order in list(self.state.orders.items()):
            info = self.service.get_order_info(symbol, order_id)
            if not info:
                continue
            status = info.get("orderStatus")
            if status == "Filled":
                await self._handle_order_filled(order_id, order, info)
            elif status == "Cancelled":
                self.state.log(f"Ордер {order_id} отменён биржей")
                self.state.remove_order(order_id)

    async def _handle_order_filled(self, order_id: str, order: OrderInfo, payload: dict) -> None:
        self.state.mark_order_filled(order_id)
        filled_qty = float(payload.get("cumExecQty") or order.qty)
        if order.order_type is OrderType.ENTRY_LONG:
            self.state.long_position_size += filled_qty
            self.state.log(f"Лонг открыт, объём {filled_qty}")
        elif order.order_type is OrderType.ENTRY_SHORT:
            self.state.short_position_size += filled_qty
            self.state.log(f"Шорт открыт, объём {filled_qty}")
        elif order.order_type is OrderType.TAKE_PROFIT:
            if order.position_side == "long":
                self.state.long_position_size = max(0.0, self.state.long_position_size - filled_qty)
            else:
                self.state.short_position_size = max(0.0, self.state.short_position_size - filled_qty)
            self.state.log(f"Тейк-профит {order.tag or ''} исполнен на {filled_qty}")
            await self._handle_take_profit_post_actions(order)
        elif order.order_type is OrderType.STOP_LOSS:
            if order.position_side == "long":
                self.state.long_position_size = max(0.0, self.state.long_position_size - filled_qty)
            else:
                self.state.short_position_size = max(0.0, self.state.short_position_size - filled_qty)
            self.state.log(f"Стоп-лосс {order.tag or ''} исполнен на {filled_qty}")
            await self._handle_stop_loss_post_actions(order, Decimal(str(filled_qty)))
        elif order.order_type is OrderType.REFILL:
            if order.position_side == "long":
                self.state.long_position_size += filled_qty
            else:
                self.state.short_position_size += filled_qty
            self.state.log(f"Доливка {order.tag or ''} исполнена на {filled_qty}")
        self.state.remove_order(order_id)

        if self.state.status == InstrumentStatus.WAITING_ENTRY:
            if (
                self._entry_orders.long_id
                and self._entry_orders.short_id
                and order_id in {self._entry_orders.long_id, self._entry_orders.short_id}
            ):
                both_filled = self.state.long_position_size > 0 and self.state.short_position_size > 0
                if both_filled:
                    await self._after_entry_filled()

    async def _after_entry_filled(self) -> None:
        self.state.status = InstrumentStatus.POSITION_OPEN
        self.state.log("Обе стороны позиции открыты. Выставляем тейк-профиты и стоп-лоссы")
        await self._place_post_entry_orders("long", self.config.long)
        await self._place_post_entry_orders("short", self.config.short)

    async def _place_post_entry_orders(self, side: str, config: SideConfig) -> None:
        symbol = self.config.symbol
        base_qty = self._entry_qty or Decimal("0")
        if base_qty <= 0:
            return
        position_idx = 1 if side == "long" else 2
        closing_side = "Sell" if side == "long" else "Buy"
        for index, tp in enumerate(config.take_profits, start=1):
            qty = (base_qty * tp.quantity_pct / Decimal("100")).quantize(Decimal("0.00000001"))
            qty = self.service.quantise_qty(symbol, qty)
            if qty <= 0:
                continue
            price = self.service.quantise_price(symbol, tp.price)
            order_id = self.service.place_limit_reduce_order(symbol, closing_side, qty, price, position_idx)
            tag = f"{side}_tp{index}"
            self._register_order(order_id, OrderType.TAKE_PROFIT, closing_side, side, float(qty), float(price), tag)
            self.state.log(f"Выставлен TP{index} для {side} qty={qty} price={price}")

        trigger_direction = 2 if side == "long" else 1
        for index, sl in enumerate(config.stop_losses, start=1):
            qty = (base_qty * sl.quantity_pct / Decimal("100")).quantize(Decimal("0.00000001"))
            if qty <= 0:
                continue
            qty = self.service.quantise_qty(symbol, qty)
            price = self.service.quantise_price(symbol, sl.trigger_price)
            order_id = self.service.place_stop_market(
                symbol=symbol,
                side=closing_side,
                qty=qty,
                trigger_price=price,
                trigger_direction=trigger_direction,
                trigger_by=self.config.trigger_by,
                position_idx=position_idx,
            )
            tag = f"{side}_sl{index}"
            self._register_order(order_id, OrderType.STOP_LOSS, closing_side, side, float(qty), float(price), tag)
            self.state.log(f"Выставлен SL{index} для {side} qty={qty} trigger={price}")

    async def _handle_take_profit_post_actions(self, order: OrderInfo) -> None:
        if order.tag and order.tag.endswith("tp1") and self.config.refill_after_tp1.enabled:
            await self._place_manual_refill(order.position_side)
        await self._check_full_exit(order.position_side)

    async def _handle_stop_loss_post_actions(self, order: OrderInfo, qty: Decimal) -> None:
        await self._place_refill_at_entry(order.position_side, qty)
        await self._check_full_exit(order.position_side)

    async def _place_manual_refill(self, side: str) -> None:
        cfg = self.config.refill_after_tp1
        if not cfg.enabled or cfg.price is None or cfg.quantity is None:
            return
        symbol = self.config.symbol
        qty = self.service.convert_usdt_to_qty(symbol, cfg.quantity, cfg.price)
        price = self.service.quantise_price(symbol, cfg.price)
        position_idx = 1 if side == "long" else 2
        side_name = "Buy" if side == "long" else "Sell"
        order_id = self.service.place_limit_order(symbol, side_name, qty, price, position_idx, reduce_only=False)
        tag = f"{side}_refill_tp1"
        self._register_order(order_id, OrderType.REFILL, side_name, side, float(qty), float(price), tag)
        self.state.log(f"Выставлена доливка после TP1 {order_id} qty={qty} price={price}")

    async def _place_refill_at_entry(self, side: str, qty: Decimal) -> None:
        symbol = self.config.symbol
        price = self.config.entry_trigger_price
        position_idx = 1 if side == "long" else 2
        order_side = "Buy" if side == "long" else "Sell"
        qty = self.service.quantise_qty(symbol, qty)
        price = self.service.quantise_price(symbol, price)
        order_id = self.service.place_limit_order(symbol, order_side, qty, price, position_idx, reduce_only=False)
        tag = f"{side}_refill_sl"
        self._register_order(order_id, OrderType.REFILL, order_side, side, float(qty), float(price), tag)
        self.state.log(f"Доливка после стопа: {order_id} qty={qty} price={price}")

    async def _check_full_exit(self, side: str) -> None:
        if side == "long" and self.state.long_position_size <= 0:
            await self._cancel_remaining_orders_for_side("long")
        if side == "short" and self.state.short_position_size <= 0:
            await self._cancel_remaining_orders_for_side("short")
        if self.state.long_position_size <= 0 and self.state.short_position_size <= 0:
            self.state.status = InstrumentStatus.IDLE
            self.state.log("Все позиции закрыты. Сделка завершена")

    async def _cancel_remaining_orders_for_side(self, side: str) -> None:
        for order_id, order in list(self.state.orders.items()):
            if order.position_side == side:
                try:
                    self.service.cancel_order(self.config.symbol, order_id)
                except Exception as exc:  # noqa: BLE001
                    self.state.log(f"Ошибка отмены ордера {order_id}: {exc}")
                self.state.remove_order(order_id)
