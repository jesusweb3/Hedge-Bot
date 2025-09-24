"""Management layer coordinating Hedge-Bot instruments."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from .bybit_service import BybitService
from .config import InstrumentConfig
from .instrument import HedgeInstrument
from .state import InstrumentState


@dataclass
class ManagedInstrument:
    symbol: str
    config: InstrumentConfig
    controller: HedgeInstrument


class HedgeBotEngine:
    """Facade managing instruments and providing control primitives."""

    def __init__(self, service: BybitService | None = None) -> None:
        self._service = service or BybitService()
        self._instruments: Dict[str, ManagedInstrument] = {}
        self._lock = asyncio.Lock()

    def list_symbols(self) -> Iterable[str]:
        return list(self._instruments)

    def get_state(self, symbol: str) -> Optional[InstrumentState]:
        instrument = self._instruments.get(symbol)
        if instrument:
            return instrument.controller.state
        return None

    async def add_instrument(self, config: InstrumentConfig) -> None:
        async with self._lock:
            symbol = config.symbol
            if symbol in self._instruments:
                raise ValueError(f"Instrument {symbol} already exists")
            controller = HedgeInstrument(config, self._service)
            self._instruments[symbol] = ManagedInstrument(symbol, config, controller)

    async def remove_instrument(self, symbol: str) -> None:
        async with self._lock:
            managed = self._instruments.pop(symbol, None)
            if managed:
                await managed.controller.stop()

    async def start_instrument(self, symbol: str) -> None:
        managed = self._instruments.get(symbol)
        if not managed:
            raise ValueError(f"Instrument {symbol} not found")
        await managed.controller.start()

    async def stop_instrument(self, symbol: str) -> None:
        managed = self._instruments.get(symbol)
        if not managed:
            raise ValueError(f"Instrument {symbol} not found")
        await managed.controller.stop()

    async def start_all(self) -> None:
        await asyncio.gather(*(inst.controller.start() for inst in self._instruments.values()))

    async def stop_all(self) -> None:
        await asyncio.gather(*(inst.controller.stop() for inst in self._instruments.values()))

    def get_instruments(self) -> Iterable[ManagedInstrument]:
        return list(self._instruments.values())
