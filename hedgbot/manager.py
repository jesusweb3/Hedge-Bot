"""Fleet management for multiple Hedg-Bot instances."""
from __future__ import annotations

import asyncio
from typing import Dict, Iterable

from .bot import HedgeBot
from .models import InstrumentConfig, ManagerState, TakeProfitLevel


def default_config(symbol: str) -> InstrumentConfig:
    """Return a sensible default configuration for a symbol."""

    return InstrumentConfig(
        symbol=symbol,
        entry_amount=100.0,
        take_profits=[
            TakeProfitLevel(label="TP1", offset_percent=0.5, volume_percent=50),
            TakeProfitLevel(label="TP2", offset_percent=1.0, volume_percent=50),
        ],
        stop_losses=[],
    )


class BotManager:
    """Coordinates a set of bots and exposes convenience helpers."""

    def __init__(self, configs: Iterable[InstrumentConfig]) -> None:
        self._bots: Dict[str, HedgeBot] = {
            config.symbol: HedgeBot(config) for config in configs
        }
        self._lock = asyncio.Lock()

    def symbols(self) -> list[str]:
        """Return the list of registered symbols."""

        return list(self._bots.keys())

    def get_bot(self, symbol: str) -> HedgeBot:
        try:
            return self._bots[symbol]
        except KeyError as exc:
            raise KeyError(f"Unknown instrument {symbol}") from exc

    async def start(self, symbol: str) -> None:
        await self.get_bot(symbol).start()

    async def stop(self, symbol: str) -> None:
        await self.get_bot(symbol).stop()

    async def close(self, symbol: str) -> None:
        await self.get_bot(symbol).close_all()

    async def start_all(self) -> None:
        async with self._lock:
            await asyncio.gather(
                *(bot.start() for bot in self._bots.values() if not bot.snapshot().is_running)
            )

    async def stop_all(self) -> None:
        async with self._lock:
            await asyncio.gather(*(bot.stop() for bot in self._bots.values()))

    def snapshot(self) -> ManagerState:
        return ManagerState(
            instruments=[bot.snapshot() for bot in self._bots.values()]
        )

    async def update_config(self, symbol: str, config: InstrumentConfig) -> None:
        await self.get_bot(symbol).update_config(config)


__all__ = ["BotManager", "default_config"]
