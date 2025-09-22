"""A lightweight Bybit HTTP client abstraction."""
from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass
from typing import Optional

from ..models import Order, OrderSide, OrderStatus, OrderType


@dataclass
class OrderRequest:
    """Request payload used by the mock client."""

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None


class MockBybitClient:
    """A stand-in for the real Bybit client.

    The mock is intentionally simple: it records the orders that would have been
    placed and immediately returns synthetic identifiers. This keeps the
    application fully testable without requiring real exchange access.
    """

    _id_counter = itertools.count(1)

    async def place_order(self, request: OrderRequest) -> Order:
        """Return a fake order object."""

        await asyncio.sleep(0)  # allow context switch in async flows
        order_id = f"{request.order_type.value}-{next(self._id_counter)}"
        return Order(
            id=order_id,
            type=request.order_type,
            side=request.side,
            price=request.price,
            quantity=request.quantity,
            status=OrderStatus.PENDING,
        )

    async def cancel_all(self, symbol: str) -> None:
        """Pretend to cancel orders on the exchange."""

        await asyncio.sleep(0)

    async def close_position(self, symbol: str, side: OrderSide) -> None:
        """Pretend to close a position at market."""

        await asyncio.sleep(0)


__all__ = ["MockBybitClient", "OrderRequest"]
