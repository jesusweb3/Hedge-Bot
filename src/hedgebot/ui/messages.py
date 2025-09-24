from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from textual.message import Message

from ..config import InstrumentSettings
from ..events import InstrumentEvent


class InstrumentEventMessage(Message):
    def __init__(self, instrument_id: str, event: InstrumentEvent) -> None:
        super().__init__()
        self.instrument_id = instrument_id
        self.event = event


@dataclass(slots=True)
class InstrumentCommand:
    instrument_id: str
    command: Literal["start", "stop", "close", "update", "remove"]
    settings: Optional[InstrumentSettings] = None


class InstrumentCommandMessage(Message):
    def __init__(self, payload: InstrumentCommand) -> None:
        super().__init__()
        self.payload = payload


class AddInstrumentMessage(Message):
    def __init__(self, settings: InstrumentSettings) -> None:
        super().__init__()
        self.settings = settings
