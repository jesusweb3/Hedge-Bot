"""Main Flet application for Hedge-Bot."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import uuid
from typing import Dict, Optional

import flet as ft

from ..bybit_client import BybitClient
from ..config import InstrumentSettings, RefillConfig, StopLossLevel, TakeProfitLevel
from ..engine import InstrumentEngine
from ..events import LogEvent, OrdersEvent, StatusEvent
from ..state import InstrumentStatus
from .add_instrument import AddInstrumentDialog
from .instrument_widget import InstrumentCard


class HedgeBotFletApp:
    """Controller that wires business logic with the Flet UI."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.client: Optional[BybitClient] = None
        self.engines: Dict[str, InstrumentEngine] = {}
        self.widgets: Dict[str, InstrumentCard] = {}
        self.event_tasks: Dict[str, asyncio.Task[None]] = {}
        self.status_text = ft.Text("Инициализация...", selectable=True)
        self.instrument_column = ft.Column(
            spacing=15,
            expand=1,
            scroll=ft.ScrollMode.AUTO,
        )
        self._instrument_counter = 1

    async def initialize(self) -> None:
        """Configure page settings and initialize API client."""

        self.page.title = "Hedge-Bot"
        self.page.padding = 20
        self.page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
        self.page.vertical_alignment = ft.MainAxisAlignment.START

        add_button = ft.FilledButton("Добавить инструмент", icon=ft.icons.ADD, on_click=self._on_add_clicked)
        start_all = ft.ElevatedButton("Запустить все", icon=ft.icons.PLAY_ARROW, on_click=self._on_start_all)
        stop_all = ft.OutlinedButton("Остановить все", icon=ft.icons.STOP_CIRCLE, on_click=self._on_stop_all)

        layout = ft.Column(
            controls=[
                ft.ResponsiveRow(
                    controls=[
                        ft.Container(add_button, col={'xs': 12, 'sm': 6, 'md': 4}),
                        ft.Container(start_all, col={'xs': 12, 'sm': 6, 'md': 4}),
                        ft.Container(stop_all, col={'xs': 12, 'sm': 6, 'md': 4}),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
                self.status_text,
                self.instrument_column,
            ],
            expand=1,
            spacing=20,
        )
        self.page.add(layout)

        try:
            self.client = BybitClient()
            self.status_text.value = "API клиента инициализирован."
        except Exception as exc:  # pylint: disable=broad-except
            self.status_text.value = f"Ошибка инициализации API: {exc}"

        self.page.on_close = self._on_page_close
        self.page.on_disconnect = self._on_page_close
        await self.page.update_async()

    async def _on_page_close(self, _event: Optional[ft.ControlEvent]) -> None:
        await self.shutdown()

    async def shutdown(self) -> None:
        """Cancel background tasks when the UI is closed."""

        for task in list(self.event_tasks.values()):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self.event_tasks.clear()

    async def _on_add_clicked(self, _event: ft.ControlEvent) -> None:
        if not self.client:
            self.status_text.value = "API клиент недоступен. Проверьте настройки .env"
            await self.page.update_async()
            return
        dialog = AddInstrumentDialog(self.page, self._default_settings(), self.create_instrument)
        await dialog.open()

    async def _on_start_all(self, _event: ft.ControlEvent) -> None:
        await self._run_for_all("start")

    async def _on_stop_all(self, _event: ft.ControlEvent) -> None:
        await self._run_for_all("stop")

    async def create_instrument(self, settings: InstrumentSettings) -> None:
        """Instantiate trading engine and create visual card for it."""

        if not self.client:
            self.status_text.value = "API клиент недоступен"
            await self.page.update_async()
            return

        instrument_id = f"{settings.symbol}-{self._instrument_counter}-{uuid.uuid4().hex[:4]}"
        self._instrument_counter += 1

        engine = InstrumentEngine(settings, self.client)
        widget = InstrumentCard(self, instrument_id, settings, engine)

        self.engines[instrument_id] = engine
        self.widgets[instrument_id] = widget
        self.instrument_column.controls.append(widget.control)
        await self.page.update_async()

        task = asyncio.create_task(self._consume_events(instrument_id, engine))
        self.event_tasks[instrument_id] = task

        await engine.events.put(StatusEvent(settings.symbol, datetime.now(UTC), InstrumentStatus.CONFIGURED, "Инструмент создан"))
        await engine.events.put(OrdersEvent(settings.symbol, datetime.now(UTC), []))
        await engine.events.put(LogEvent(settings.symbol, datetime.now(UTC), "info", "Инструмент добавлен"))

    async def _consume_events(self, instrument_id: str, engine: InstrumentEngine) -> None:
        """Consume engine events and forward them to UI widgets."""

        try:
            while True:
                event = await engine.events.get()
                widget = self.widgets.get(instrument_id)
                if widget:
                    await widget.handle_event(event)
        except asyncio.CancelledError:
            pass

    async def run_command(self, instrument_id: str, command: str, settings: Optional[InstrumentSettings] = None) -> Optional[str]:
        """Execute a command on an instrument engine."""

        engine = self.engines.get(instrument_id)
        if not engine:
            return "Инструмент не найден"
        try:
            if command == "start":
                await engine.start()
            elif command == "stop":
                await engine.stop()
            elif command == "close":
                await engine.close_all()
            elif command == "update" and settings:
                await engine.update_settings(settings)
            elif command == "remove":
                await self.remove_instrument(instrument_id)
        except RuntimeError as exc:
            await engine.events.put(
                LogEvent(engine.settings.symbol, datetime.now(UTC), "error", f"Ошибка команды: {exc}")
            )
            return str(exc)
        return None

    async def remove_instrument(self, instrument_id: str) -> None:
        """Remove card, stop tasks and clean resources."""

        engine = self.engines.pop(instrument_id, None)
        widget = self.widgets.pop(instrument_id, None)
        task = self.event_tasks.pop(instrument_id, None)

        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        if engine:
            with suppress(RuntimeError):
                await engine.stop()

        if widget and widget.control in self.instrument_column.controls:
            self.instrument_column.controls.remove(widget.control)
            await self.page.update_async()

    async def _run_for_all(self, command: str) -> None:
        tasks = [self.run_command(iid, command) for iid in list(self.engines.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _default_settings() -> InstrumentSettings:
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


async def _main(page: ft.Page) -> None:
    app = HedgeBotFletApp(page)
    await app.initialize()


def run_app() -> None:
    ft.app(target=_main)
