# src/hedgebot/ui/add_instrument.py
"""
Модальное окно для добавления нового торгового инструмента.
Содержит форму с настройками символа, объёмов, тейк-профитов, стоп-лоссов и доливок.
Валидирует входные данные и отправляет сообщение с настройками в главное приложение.
"""

from __future__ import annotations

from typing import List

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Select, Static

from ..config import InstrumentSettings, RefillConfig, StopLossLevel, TakeProfitLevel
from .messages import AddInstrumentMessage


class AddInstrumentScreen(ModalScreen[None]):
    """Диалог добавления нового инструмента."""

    def __init__(self, defaults: InstrumentSettings) -> None:
        super().__init__()
        self.defaults = defaults.clone()
        self.message_label = Static("", classes="settings-message")

        self.symbol_input = Input(value=self.defaults.symbol, placeholder="BTCUSDT")
        self.quantity_input = Input(value=str(self.defaults.base_quantity), placeholder="Базовый объём")
        self.trigger_price_input = Input(value=str(self.defaults.entry_trigger_price), placeholder="Цена триггера")
        self.trigger_direction_select = Select(
            options=[("Price >=", "1"), ("Price <=", "2")],
            value=str(self.defaults.entry_trigger_direction),
        )
        self.trigger_by_select = Select(
            options=[("Last", "LastPrice"), ("Mark", "MarkPrice"), ("Index", "IndexPrice")],
            value=self.defaults.trigger_by,
        )
        self.tp1_offset_input = Input(value=str(self.defaults.take_profits[0].offset_percent))
        self.tp1_qty_input = Input(value=str(self.defaults.take_profits[0].quantity_percent))
        self.tp2_offset_input = Input(value=str(self.defaults.take_profits[1].offset_percent))
        self.tp2_qty_input = Input(value=str(self.defaults.take_profits[1].quantity_percent))
        stops_default = ",".join(f"{sl.offset_percent}:{sl.quantity_percent}" for sl in self.defaults.stop_losses)
        self.stop_pairs_input = Input(value=stops_default, placeholder="0.5:30,1.0:30")
        self.refill_checkbox = Checkbox(label="Доливка после TP1", value=self.defaults.refill.enabled_after_tp1)
        self.refill_price_input = Input(value=str(self.defaults.refill.price_offset_percent))
        self.refill_qty_input = Input(value=str(self.defaults.refill.quantity_percent))

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-body"):
            yield Static("Добавление инструмента", classes="modal-title")
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
            yield self.message_label
            with Horizontal():
                yield Button("Создать", id="create", variant="success")
                yield Button("Отмена", id="cancel", variant="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "create":
            try:
                settings = self._collect_settings()
                self.post_message(AddInstrumentMessage(settings))
                self.message_label.set_classes("settings-message success")
                self.message_label.update("Инструмент создан")
                self.dismiss(None)
            except Exception as exc:  # pylint: disable=broad-except
                self.message_label.set_classes("settings-message error")
                self.message_label.update(f"Ошибка: {exc}")

    def _collect_settings(self) -> InstrumentSettings:
        symbol = self.symbol_input.value.strip().upper()
        base_qty = float(self.quantity_input.value)
        trigger_price = float(self.trigger_price_input.value)
        trigger_direction = int(self.trigger_direction_select.value or 2)
        trigger_by = self.trigger_by_select.value or "LastPrice"
        tp1 = TakeProfitLevel(offset_percent=float(self.tp1_offset_input.value), quantity_percent=float(self.tp1_qty_input.value))
        tp2 = TakeProfitLevel(offset_percent=float(self.tp2_offset_input.value), quantity_percent=float(self.tp2_qty_input.value))
        stops = self._parse_stop_levels(self.stop_pairs_input.value)
        refill = RefillConfig(
            enabled_after_tp1=self.refill_checkbox.value,
            price_offset_percent=float(self.refill_price_input.value or 0),
            quantity_percent=float(self.refill_qty_input.value or 0),
        )
        settings = InstrumentSettings(
            symbol=symbol,
            base_quantity=base_qty,
            entry_trigger_price=trigger_price,
            entry_trigger_direction=trigger_direction,
            trigger_by=trigger_by,
            take_profits=[tp1, tp2],
            stop_losses=stops,
            refill=refill,
        )
        settings.validate()
        return settings

    @staticmethod
    def _parse_stop_levels(value: str) -> List[StopLossLevel]:
        parts = [p.strip() for p in (value or "").split(",") if p.strip()]
        if not parts:
            raise ValueError("Необходимо указать хотя бы один стоп-лосс")
        levels: List[StopLossLevel] = []
        for part in parts:
            if ":" not in part:
                raise ValueError("Неверный формат стопов. Используйте offset:qty")
            offset_str, qty_str = part.split(":", 1)
            levels.append(StopLossLevel(offset_percent=float(offset_str), quantity_percent=float(qty_str)))
        return levels