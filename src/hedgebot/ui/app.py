from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime
import uuid
from typing import Dict, Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Static

from ..config import InstrumentSettings, RefillConfig, StopLossLevel, TakeProfitLevel
from ..events import LogEvent, OrdersEvent, StatusEvent
from ..state import InstrumentStatus
from ..bybit_client import BybitClient
from ..engine import InstrumentEngine
from .add_instrument import AddInstrumentScreen
from .instrument_widget import InstrumentWidget
from .messages import (
    AddInstrumentMessage,
    InstrumentCommand,
    InstrumentCommandMessage,
    InstrumentEventMessage,
)


class HedgeBotApp(App):
    CSS_PATH = "app.css"

    BINDINGS = [
        ("a", "open_add_dialog", "Добавить инструмент"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.client: Optional[BybitClient] = None
        self.engines: Dict[str, InstrumentEngine] = {}
        self.widgets: Dict[str, InstrumentWidget] = {}
        self.event_tasks: Dict[str, asyncio.Task] = {}
        self.status_label: Static | None = None
        self.instrument_container: Vertical | None = None
        self._instrument_counter = 1

    def compose(self) -> ComposeResult:
        self.status_label = Static("", classes="client-status")
        self.instrument_container = Vertical(id="instrument-container")

        yield Header(show_clock=True)
        with Vertical(id="main-layout"):
            with Horizontal(id="control-bar"):
                yield Button("Добавить инструмент", id="add", variant="primary")
                yield Button("Запустить все", id="start-all", variant="success")
                yield Button("Остановить все", id="stop-all", variant="warning")
            yield self.status_label
            yield VerticalScroll(self.instrument_container, id="instrument-scroll")
        yield Footer()

    async def on_mount(self) -> None:
        try:
            self.client = BybitClient()
            self.status_label.update("API клиента инициализирован.")
        except Exception as exc:  # pylint: disable=broad-except
            self.status_label.update(f"Ошибка инициализации API: {exc}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add":
            await self.action_open_add_dialog()
        elif event.button.id == "start-all":
            await self._run_for_all("start")
        elif event.button.id == "stop-all":
            await self._run_for_all("stop")

    async def action_open_add_dialog(self) -> None:
        if not self.client:
            self.status_label.update("API клиент недоступен. Проверьте настройки .env")
            return
        defaults = self._default_settings()
        await self.push_screen(AddInstrumentScreen(defaults))

    async def on_add_instrument_message(self, message: AddInstrumentMessage) -> None:
        await self._create_instrument(message.settings)

    async def on_instrument_command_message(self, message: InstrumentCommandMessage) -> None:
        payload = message.payload
        if payload.command == "remove":
            await self._remove_instrument(payload.instrument_id)
            return
        await self._run_command(payload)

    async def on_instrument_event_message(self, event: InstrumentEventMessage) -> None:
        widget = self.widgets.get(event.instrument_id)
        if widget:
            await widget.post_message(event)

    async def _create_instrument(self, settings: InstrumentSettings) -> None:
        if not self.client:
            self.status_label.update("API клиент недоступен")
            return
        instrument_id = f"{settings.symbol}-{self._instrument_counter}-{uuid.uuid4().hex[:4]}"
        self._instrument_counter += 1
        container = self.instrument_container
        if not container:
            return
        engine = InstrumentEngine(settings, self.client)
        widget = InstrumentWidget(instrument_id, settings)
        self.engines[instrument_id] = engine
        self.widgets[instrument_id] = widget
        await container.mount(widget)
        task = self.add_background_task(self._consume_events(instrument_id, engine))
        self.event_tasks[instrument_id] = task
        await engine.events.put(StatusEvent(settings.symbol, datetime.utcnow(), InstrumentStatus.CONFIGURED, "Инструмент создан"))
        await engine.events.put(OrdersEvent(settings.symbol, datetime.utcnow(), []))
        await engine.events.put(LogEvent(settings.symbol, datetime.utcnow(), "info", "Инструмент добавлен"))

    async def _consume_events(self, instrument_id: str, engine: InstrumentEngine) -> None:
        while True:
            event = await engine.events.get()
            await self.post_message(InstrumentEventMessage(instrument_id, event))

    async def _run_command(self, payload: InstrumentCommand) -> None:
        engine = self.engines.get(payload.instrument_id)
        if not engine:
            return
        try:
            if payload.command == "start":
                await engine.start()
            elif payload.command == "stop":
                await engine.stop()
            elif payload.command == "close":
                await engine.close_all()
            elif payload.command == "update" and payload.settings:
                await engine.update_settings(payload.settings)
        except Exception as exc:  # pylint: disable=broad-except
            await engine.events.put(LogEvent(engine.settings.symbol, datetime.utcnow(), "error", f"Ошибка команды: {exc}"))

    async def _remove_instrument(self, instrument_id: str) -> None:
        engine = self.engines.pop(instrument_id, None)
        widget = self.widgets.pop(instrument_id, None)
        task = self.event_tasks.pop(instrument_id, None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if engine:
            try:
                await engine.stop()
            except Exception:  # pylint: disable=broad-except
                pass
        if widget:
            widget.remove()

    async def _run_for_all(self, command: str) -> None:
        tasks = []
        for iid in list(self.engines.keys()):
            payload = InstrumentCommand(iid, command)
            tasks.append(self._run_command(payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _default_settings(self) -> InstrumentSettings:
        return InstrumentSettings(
            symbol="BTCUSDT",
            base_quantity=0.001,
            entry_trigger_price=25000.0,
            entry_trigger_direction=2,
            trigger_by="LastPrice",
            take_profits=[
                TakeProfitLevel(offset_percent=0.5, quantity_percent=50.0),
                TakeProfitLevel(offset_percent=1.0, quantity_percent=50.0),
            ],
            stop_losses=[
                StopLossLevel(offset_percent=0.5, quantity_percent=50.0),
                StopLossLevel(offset_percent=1.0, quantity_percent=50.0),
            ],
            refill=RefillConfig(enabled_after_tp1=False, price_offset_percent=0.2, quantity_percent=25.0),
        )


def run_app() -> None:
    app = HedgeBotApp()
    app.run()