# src/hedgebot/ui/instrument_widget.py
"""
Виджет инструмента с вкладками для управления торговыми настройками.
Содержит четыре вкладки: Настройки, Статус, Ордеры и Лог.
Обрабатывает пользовательский ввод, отображает состояние торговли,
показывает активные ордера и ведет журнал событий.
"""

from __future__ import annotations

from typing import List

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Select,
    Static,
    TabPane,
    TabbedContent,
    RichLog,
)

from ..config import InstrumentSettings, RefillConfig, StopLossLevel, TakeProfitLevel
from ..events import LogEvent, OrdersEvent, StatusEvent
from ..state import InstrumentStatus, ManagedOrder
from .messages import InstrumentCommand, InstrumentCommandMessage, InstrumentEventMessage


class InstrumentWidget(Vertical):
    """Виджет с вкладками для одного инструмента."""

    def __init__(self, instrument_id: str, settings: InstrumentSettings) -> None:
        super().__init__(id=f"instrument-{instrument_id}")
        self.instrument_id = instrument_id
        self.settings = settings.clone()

        # Настройки формы
        self.symbol_input = Input(value=self.settings.symbol, placeholder="BTCUSDT", id=f"{instrument_id}-symbol")
        self.quantity_input = Input(value=str(self.settings.base_quantity), placeholder="Базовый объём", id=f"{instrument_id}-qty")
        self.trigger_price_input = Input(value=str(self.settings.entry_trigger_price), placeholder="Цена триггера", id=f"{instrument_id}-trigger-price")
        self.trigger_direction_select = Select(
            options=[("Price >=", "1"), ("Price <=", "2")],
            value=str(self.settings.entry_trigger_direction),
            id=f"{instrument_id}-direction",
        )
        self.trigger_by_select = Select(
            options=[("Last", "LastPrice"), ("Mark", "MarkPrice"), ("Index", "IndexPrice")],
            value=self.settings.trigger_by,
            id=f"{instrument_id}-trigger-by",
        )
        self.tp1_offset_input = Input(value=str(self.settings.take_profits[0].offset_percent), placeholder="TP1 %", id=f"{instrument_id}-tp1-offset")
        self.tp1_qty_input = Input(value=str(self.settings.take_profits[0].quantity_percent), placeholder="TP1 объём %", id=f"{instrument_id}-tp1-qty")
        self.tp2_offset_input = Input(value=str(self.settings.take_profits[1].offset_percent), placeholder="TP2 %", id=f"{instrument_id}-tp2-offset")
        self.tp2_qty_input = Input(value=str(self.settings.take_profits[1].quantity_percent), placeholder="TP2 объём %", id=f"{instrument_id}-tp2-qty")
        stops_default = ",".join(f"{sl.offset_percent}:{sl.quantity_percent}" for sl in self.settings.stop_losses)
        self.stop_pairs_input = Input(value=stops_default, placeholder="0.5:30,1.0:30,1.5:40", id=f"{instrument_id}-stops")
        self.refill_checkbox = Checkbox(label="Доливка после TP1", value=self.settings.refill.enabled_after_tp1, id=f"{instrument_id}-refill-enabled")
        self.refill_price_input = Input(value=str(self.settings.refill.price_offset_percent), placeholder="Смещение цены %", id=f"{instrument_id}-refill-price")
        self.refill_qty_input = Input(value=str(self.settings.refill.quantity_percent), placeholder="Объём %", id=f"{instrument_id}-refill-qty")
        self.settings_message = Static("", classes="settings-message")
        self.title_label = Static(f"Инструмент {self.settings.symbol}", classes="instrument-title")

        # Статус и управление
        self.status_label = Static("Статус: CONFIGURED", classes="status-label")
        self.status_details = Static("", classes="status-details")
        self.start_button = Button("Старт", id=f"{instrument_id}-start", variant="success")
        self.stop_button = Button("Стоп", id=f"{instrument_id}-stop", variant="warning")
        self.close_button = Button("Закрыть всё", id=f"{instrument_id}-close", variant="error")
        self.remove_button = Button("Удалить", id=f"{instrument_id}-remove", variant="primary")

        # Ордеры и лог
        self.orders_table = DataTable(id=f"{instrument_id}-orders")
        self.orders_table.add_columns(
            "ID", "Тип", "Сторона", "Позиция", "Кол-во", "Цена", "Триггер", "RO", "Статус", "Обновлено"
        )
        self.log_view = RichLog(id=f"{instrument_id}-log", highlight=True, markup=True)
        self.log_view.max_lines = 500
        self._update_button_states(InstrumentStatus.CONFIGURED)

    def compose(self) -> ComposeResult:
        yield self.title_label
        with TabbedContent(id=f"tabs-{self.instrument_id}"):
            with TabPane("Настройки", id=f"{self.instrument_id}-settings-tab"):
                yield from self._compose_settings_tab()
            with TabPane("Статус", id=f"{self.instrument_id}-status-tab"):
                yield from self._compose_status_tab()
            with TabPane("Ордеры", id=f"{self.instrument_id}-orders-tab"):
                yield from self._compose_orders_tab()
            with TabPane("Лог", id=f"{self.instrument_id}-log-tab"):
                yield from self._compose_log_tab()

    # ------------------------------------------------------------------
    # Компоненты вкладок
    # ------------------------------------------------------------------
    def _compose_settings_tab(self) -> ComposeResult:
        with Grid(classes="settings-grid"):
            yield Static("Символ")
            yield self.symbol_input
            yield Static("Базовый объём")
            yield self.quantity_input
            yield Static("Цена входа")
            yield self.trigger_price_input
            yield Static("Направление триггера")
            yield self.trigger_direction_select
            yield Static("Триггер по")
            yield self.trigger_by_select
            yield Static("TP1 %")
            yield self.tp1_offset_input
            yield Static("TP1 объём %")
            yield self.tp1_qty_input
            yield Static("TP2 %")
            yield self.tp2_offset_input
            yield Static("TP2 объём %")
            yield self.tp2_qty_input
            yield Static("Стопы offset:qty")
            yield self.stop_pairs_input
            yield self.refill_checkbox
            with Horizontal():
                yield Static("Цена доливки %")
                yield self.refill_price_input
                yield Static("Объём %")
                yield self.refill_qty_input
            yield self.settings_message
            yield Button("Сохранить", id=f"{self.instrument_id}-save", variant="success")

    def _compose_status_tab(self) -> ComposeResult:
        with Vertical(classes="status-pane"):
            yield self.status_label
            yield self.status_details
            with Horizontal():
                yield self.start_button
                yield self.stop_button
                yield self.close_button
                yield self.remove_button

    def _compose_orders_tab(self) -> ComposeResult:
        yield self.orders_table

    def _compose_log_tab(self) -> ComposeResult:
        yield self.log_view

    # ------------------------------------------------------------------
    # События
    # ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.endswith("-start"):
            self.post_message(InstrumentCommandMessage(InstrumentCommand(self.instrument_id, "start")))
        elif button_id.endswith("-stop"):
            self.post_message(InstrumentCommandMessage(InstrumentCommand(self.instrument_id, "stop")))
        elif button_id.endswith("-close"):
            self.post_message(InstrumentCommandMessage(InstrumentCommand(self.instrument_id, "close")))
        elif button_id.endswith("-remove"):
            self.post_message(InstrumentCommandMessage(InstrumentCommand(self.instrument_id, "remove")))
        elif button_id.endswith("-save"):
            try:
                settings = self._collect_settings_from_form()
                self.post_message(InstrumentCommandMessage(InstrumentCommand(self.instrument_id, "update", settings)))
                self.settings = settings.clone()
                self.title_label.update(f"Инструмент {self.settings.symbol}")
                self.settings_message.set_classes("settings-message success")
                self.settings_message.update("Настройки сохранены")
            except Exception as exc:  # pylint: disable=broad-except
                self.settings_message.set_classes("settings-message error")
                self.settings_message.update(f"Ошибка: {exc}")

    def _collect_settings_from_form(self) -> InstrumentSettings:
        symbol = self.symbol_input.value.strip().upper()
        base_qty = float(self.quantity_input.value)
        trigger_price = float(self.trigger_price_input.value)
        trigger_direction = int(self.trigger_direction_select.value or 2)
        trigger_by = self.trigger_by_select.value or "LastPrice"
        tp1 = TakeProfitLevel(offset_percent=float(self.tp1_offset_input.value), quantity_percent=float(self.tp1_qty_input.value))
        tp2 = TakeProfitLevel(offset_percent=float(self.tp2_offset_input.value), quantity_percent=float(self.tp2_qty_input.value))
        stops = self._parse_stop_levels(self.stop_pairs_input.value)
        refill_enabled = self.refill_checkbox.value
        refill_price = float(self.refill_price_input.value or 0)
        refill_qty = float(self.refill_qty_input.value or 0)
        settings = InstrumentSettings(
            symbol=symbol,
            base_quantity=base_qty,
            entry_trigger_price=trigger_price,
            entry_trigger_direction=trigger_direction,
            trigger_by=trigger_by,
            take_profits=[tp1, tp2],
            stop_losses=stops,
            refill=RefillConfig(
                enabled_after_tp1=refill_enabled,
                price_offset_percent=refill_price,
                quantity_percent=refill_qty,
            ),
        )
        settings.validate()
        return settings

    @staticmethod
    def _parse_stop_levels(value: str) -> List[StopLossLevel]:
        parts = [p.strip() for p in (value or "").split(",") if p.strip()]
        levels: List[StopLossLevel] = []
        for part in parts:
            if ":" not in part:
                raise ValueError("Неверный формат стопов. Используйте offset:qty через запятую")
            offset_str, qty_str = part.split(":", 1)
            levels.append(StopLossLevel(offset_percent=float(offset_str), quantity_percent=float(qty_str)))
        return levels

    def on_instrument_event_message(self, event: InstrumentEventMessage) -> None:
        if event.instrument_id != self.instrument_id:
            return
        payload = event.event
        if isinstance(payload, StatusEvent):
            self._handle_status_event(payload)
        elif isinstance(payload, LogEvent):
            self._handle_log_event(payload)
        elif isinstance(payload, OrdersEvent):
            self._handle_orders_event(payload)

    def _handle_status_event(self, event: StatusEvent) -> None:
        self.status_label.update(f"Статус: {event.status.value.upper()}")
        details = event.details or ""
        self.status_details.update(details)
        self._update_button_states(event.status)

    def _handle_log_event(self, event: LogEvent) -> None:
        timestamp = event.timestamp.strftime("%H:%M:%S")
        style_map = {
            "info": "green",
            "warning": "yellow",
            "error": "red",
            "debug": "dim",
        }
        style = style_map.get(event.level, "white")
        self.log_view.write(f"[{style}][{timestamp}] {event.message}[/{style}]")

    def _handle_orders_event(self, event: OrdersEvent) -> None:
        self.orders_table.clear()
        for order in event.orders:
            self.orders_table.add_row(*self._order_to_row(order))

    @staticmethod
    def _order_to_row(order: ManagedOrder) -> List[str]:
        return [
            order.order_id[-12:],
            order.kind.value,
            order.side,
            order.position_side,
            f"{order.quantity:.6f}",
            f"{order.price:.4f}" if order.price else "-",
            f"{order.trigger_price:.4f}" if order.trigger_price else "-",
            "Y" if order.reduce_only else "N",
            order.status,
            order.updated_at.strftime("%H:%M:%S"),
        ]

    def _update_button_states(self, status: InstrumentStatus) -> None:
        self.start_button.disabled = status in {InstrumentStatus.WAITING_ENTRY, InstrumentStatus.ACTIVE}
        self.stop_button.disabled = status not in {InstrumentStatus.WAITING_ENTRY, InstrumentStatus.ACTIVE}
        self.close_button.disabled = status == InstrumentStatus.CONFIGURED