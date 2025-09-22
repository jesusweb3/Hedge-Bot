"""Core bot logic for managing a hedged position."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List

from .exchange.bybit_client import MockBybitClient, OrderRequest
from .models import (
    InstrumentConfig,
    InstrumentState,
    LogEntry,
    LogLevel,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    StopLossLevel,
    TakeProfitLevel,
)


@dataclass
class _RuntimeState:
    """Mutable runtime state maintained while the bot is active."""

    is_running: bool = False
    positions: Dict[OrderSide, float] = None  # type: ignore[assignment]
    open_orders: List[Order] = None  # type: ignore[assignment]
    dca_orders: List[Order] = None  # type: ignore[assignment]
    logs: List[LogEntry] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.positions = {OrderSide.LONG: 0.0, OrderSide.SHORT: 0.0}
        self.open_orders = []
        self.dca_orders = []
        self.logs = []


class HedgeBot:
    """Encapsulates the hedging automation for a single instrument."""

    def __init__(
        self,
        config: InstrumentConfig,
        client: MockBybitClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or MockBybitClient()
        self._lock = asyncio.Lock()
        self._state = _RuntimeState()

    @property
    def config(self) -> InstrumentConfig:
        return self._config

    async def update_config(self, config: InstrumentConfig) -> None:
        """Replace the configuration. Allowed only when stopped."""

        async with self._lock:
            if self._state.is_running:
                raise RuntimeError("Cannot change configuration while bot is running")
            self._config = config
            self._append_log("Configuration updated")

    async def start(self) -> None:
        """Start the strategy by opening both directions."""

        async with self._lock:
            if self._state.is_running:
                raise RuntimeError("Bot already running")

            await self._create_entry_orders()
            await self._create_take_profits()
            await self._create_stop_losses()

            self._state.positions[OrderSide.LONG] = self._config.entry_amount
            self._state.positions[OrderSide.SHORT] = self._config.entry_amount
            self._state.is_running = True
            self._append_log("Bot started: entry orders placed for both sides")

    async def stop(self) -> None:
        """Stop the bot and cancel all outstanding orders."""

        async with self._lock:
            if not self._state.is_running:
                return

            await self._client.cancel_all(self._config.symbol)
            self._reset_runtime(clear_logs=False)
            self._append_log("Bot stopped and orders cancelled", level=LogLevel.WARNING)

    async def close_all(self) -> None:
        """Close both sides at market and reset the state."""

        async with self._lock:
            if not self._state.is_running:
                return

            for side in (OrderSide.LONG, OrderSide.SHORT):
                await self._client.close_position(self._config.symbol, side)
                self._state.positions[side] = 0.0

            await self._client.cancel_all(self._config.symbol)
            self._reset_runtime(clear_logs=False)
            self._append_log("Positions closed manually", level=LogLevel.WARNING)

    async def trigger_take_profit(self, side: OrderSide, level_index: int) -> None:
        """Simulate take-profit fill to test the workflow."""

        async with self._lock:
            self._ensure_running()
            level = self._config.take_profits[level_index]
            await self._handle_take_profit(side, level)

    async def trigger_stop_loss(self, side: OrderSide, level_index: int) -> None:
        """Simulate stop-loss fill to test the workflow."""

        async with self._lock:
            self._ensure_running()
            level = self._config.stop_losses[level_index]
            await self._handle_stop_loss(side, level_index, level)

    async def trigger_dca_fill(self, order_id: str) -> None:
        """Mark a DCA order as filled and restore the position size."""

        async with self._lock:
            for order in self._state.dca_orders:
                if order.id == order_id and order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.FILLED
                    self._state.positions[order.side] += order.quantity
                    self._append_log(
                        f"DCA order {order.id} filled for {order.side.value}")
                    return
            raise ValueError(f"DCA order {order_id} not found or already filled")

    def snapshot(self) -> InstrumentState:
        """Return a serialisable snapshot of the current state."""

        return InstrumentState(
            symbol=self._config.symbol,
            is_running=self._state.is_running,
            positions=self._state.positions.copy(),
            open_orders=list(self._state.open_orders),
            dca_orders=list(self._state.dca_orders),
            logs=list(self._state.logs),
            config=self._config,
        )

    # Internal helpers -------------------------------------------------
    def _reset_runtime(self, clear_logs: bool = True) -> None:
        logs = [] if clear_logs else list(self._state.logs)
        self._state = _RuntimeState()
        self._state.logs = logs

    def _ensure_running(self) -> None:
        if not self._state.is_running:
            raise RuntimeError("Bot must be running to handle events")

    def _append_log(self, message: str, level: LogLevel = LogLevel.INFO) -> None:
        self._state.logs.append(LogEntry(message=message, level=level))

    async def _create_entry_orders(self) -> None:
        for side in (OrderSide.LONG, OrderSide.SHORT):
            order = await self._client.place_order(
                OrderRequest(
                    symbol=self._config.symbol,
                    side=side,
                    order_type=OrderType.ENTRY,
                    quantity=self._config.entry_amount,
                )
            )
            self._state.open_orders.append(order)
            self._append_log(
                f"Entry order created for {side.value} with size {order.quantity}")

    async def _create_take_profits(self) -> None:
        for level in self._config.take_profits:
            for side in (OrderSide.LONG, OrderSide.SHORT):
                quantity = self._config.entry_amount * level.volume_percent / 100
                order = await self._client.place_order(
                    OrderRequest(
                        symbol=self._config.symbol,
                        side=side,
                        order_type=OrderType.TAKE_PROFIT,
                        quantity=quantity,
                    )
                )
                self._state.open_orders.append(order)
                self._append_log(
                    f"{level.label} order placed for {side.value} ({quantity} contracts)")

    async def _create_stop_losses(self) -> None:
        for level in self._config.stop_losses:
            for side in (OrderSide.LONG, OrderSide.SHORT):
                quantity = self._config.entry_amount * level.volume_percent / 100
                order = await self._client.place_order(
                    OrderRequest(
                        symbol=self._config.symbol,
                        side=side,
                        order_type=OrderType.STOP_LOSS,
                        quantity=quantity,
                    )
                )
                self._state.open_orders.append(order)
                self._append_log(
                    f"Stop-loss order placed for {side.value} ({quantity} contracts)")

    async def _handle_take_profit(
        self,
        side: OrderSide,
        level: TakeProfitLevel,
    ) -> None:
        quantity = self._config.entry_amount * level.volume_percent / 100
        self._state.positions[side] = max(
            0.0, self._state.positions[side] - quantity
        )

        for order in self._state.open_orders:
            if (
                order.type == OrderType.TAKE_PROFIT
                and order.side == side
                and order.status == OrderStatus.PENDING
            ):
                order.status = OrderStatus.FILLED
                break

        self._append_log(
            f"{level.label} hit for {side.value}, closed {quantity} contracts")

        if level.label == "TP1":
            await self._maybe_create_tp1_dca(side)
        else:
            await self._finalise_trade()

    async def _handle_stop_loss(
        self,
        side: OrderSide,
        level_index: int,
        level: StopLossLevel,
    ) -> None:
        quantity = self._config.entry_amount * level.volume_percent / 100
        self._state.positions[side] = max(
            0.0, self._state.positions[side] - quantity
        )

        for order in self._state.open_orders:
            if (
                order.type == OrderType.STOP_LOSS
                and order.side == side
                and order.status == OrderStatus.PENDING
            ):
                order.status = OrderStatus.FILLED
                break

        self._append_log(
            f"Stop-loss level {level_index + 1} triggered for {side.value},"
            f" closed {quantity} contracts",
        )

        await self._create_entry_dca(side, quantity)

    async def _maybe_create_tp1_dca(self, side: OrderSide) -> None:
        if not self._config.tp1_dca.enabled:
            return
        quantity = self._config.tp1_dca.quantity or 0.0
        if quantity <= 0:
            return
        offset = self._config.tp1_dca.offset_percent or 0.0
        order = await self._client.place_order(
            OrderRequest(
                symbol=self._config.symbol,
                side=side,
                order_type=OrderType.DCA,
                quantity=quantity,
            )
        )
        self._state.dca_orders.append(order)
        self._append_log(
            f"TP1 DCA order placed for {side.value} ({order.quantity} contracts, offset {offset:.2f}%)"
        )

    async def _create_entry_dca(self, side: OrderSide, quantity: float) -> None:
        if quantity <= 0:
            return
        order = await self._client.place_order(
            OrderRequest(
                symbol=self._config.symbol,
                side=side,
                order_type=OrderType.DCA,
                quantity=quantity,
            )
        )
        self._state.dca_orders.append(order)
        self._append_log(
            f"Entry DCA order placed for {side.value} ({quantity} contracts)"
        )

    async def _finalise_trade(self) -> None:
        for order in self._state.open_orders:
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
        self._state.positions[OrderSide.LONG] = 0.0
        self._state.positions[OrderSide.SHORT] = 0.0
        self._state.is_running = False
        self._append_log("Final TP reached. Trade cycle completed.")


__all__ = ["HedgeBot"]
