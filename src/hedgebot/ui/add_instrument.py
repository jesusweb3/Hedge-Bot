"""Modal dialog for creating a new instrument in Flet UI."""
from __future__ import annotations

from typing import Awaitable, Callable, List

import flet as ft

from ..config import InstrumentSettings, RefillConfig, StopLossLevel, TakeProfitLevel


class AddInstrumentDialog:
    """Wraps an AlertDialog with form fields for instrument creation."""

    def __init__(
        self,
        page: ft.Page,
        defaults: InstrumentSettings,
        on_submit: Callable[[InstrumentSettings], Awaitable[None]],
    ) -> None:
        self.page = page
        self.defaults = defaults.clone()
        self.on_submit = on_submit

        self.symbol_input = ft.TextField(label="Символ", value=self.defaults.symbol.upper())
        self.quantity_input = ft.TextField(label="Базовый объём", value=str(self.defaults.base_quantity))
        self.trigger_price_input = ft.TextField(label="Цена входа", value=str(self.defaults.entry_trigger_price))
        self.trigger_direction_select = ft.Dropdown(
            label="Направление триггера",
            value=str(self.defaults.entry_trigger_direction),
            options=[
                ft.dropdown.Option(key="1", text="Price >="),
                ft.dropdown.Option(key="2", text="Price <="),
            ],
        )
        self.trigger_by_select = ft.Dropdown(
            label="Триггер по",
            value=self.defaults.trigger_by,
            options=[
                ft.dropdown.Option("LastPrice", "Last"),
                ft.dropdown.Option("MarkPrice", "Mark"),
                ft.dropdown.Option("IndexPrice", "Index"),
            ],
        )
        self.tp1_offset_input = ft.TextField(label="TP1 %", value=str(self.defaults.take_profits[0].offset_percent))
        self.tp1_qty_input = ft.TextField(label="TP1 объём %", value=str(self.defaults.take_profits[0].quantity_percent))
        self.tp2_offset_input = ft.TextField(label="TP2 %", value=str(self.defaults.take_profits[1].offset_percent))
        self.tp2_qty_input = ft.TextField(label="TP2 объём %", value=str(self.defaults.take_profits[1].quantity_percent))
        stops_default = ",".join(f"{sl.offset_percent}:{sl.quantity_percent}" for sl in self.defaults.stop_losses)
        self.stop_pairs_input = ft.TextField(label="Стопы offset:qty", value=stops_default)
        self.refill_checkbox = ft.Checkbox(label="Доливка после TP1", value=self.defaults.refill.enabled_after_tp1)
        self.refill_price_input = ft.TextField(label="Цена доливки %", value=str(self.defaults.refill.price_offset_percent))
        self.refill_qty_input = ft.TextField(label="Объём доливки %", value=str(self.defaults.refill.quantity_percent))
        self.message = ft.Text(value="", color=ft.colors.RED)

        content = ft.Column(
            controls=[
                self.symbol_input,
                self.quantity_input,
                self.trigger_price_input,
                self.trigger_direction_select,
                self.trigger_by_select,
                ft.Row([self.tp1_offset_input, self.tp1_qty_input]),
                ft.Row([self.tp2_offset_input, self.tp2_qty_input]),
                self.stop_pairs_input,
                self.refill_checkbox,
                ft.Row([self.refill_price_input, self.refill_qty_input]),
                self.message,
            ],
            tight=True,
            spacing=10,
        )

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Добавление инструмента"),
            content=ft.Container(content=content, width=420),
            actions=[
                ft.TextButton("Отмена", on_click=self._on_cancel),
                ft.FilledButton("Создать", icon=ft.icons.ADD, on_click=self._on_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    async def open(self) -> None:
        self.page.dialog = self.dialog
        self.dialog.open = True
        await self.page.update_async()

    async def _on_cancel(self, _event: ft.ControlEvent) -> None:
        self.dialog.open = False
        self.page.dialog = None
        await self.page.update_async()

    async def _on_submit(self, _event: ft.ControlEvent) -> None:
        try:
            settings = self._collect_settings()
        except Exception as exc:  # pylint: disable=broad-except
            self.message.value = f"Ошибка: {exc}"
            self.message.color = ft.colors.RED
            await self.page.update_async()
            return

        try:
            await self.on_submit(settings)
        except Exception as exc:  # pylint: disable=broad-except
            self.message.value = f"Ошибка создания: {exc}"
            self.message.color = ft.colors.RED
            await self.page.update_async()
            return

        self.dialog.open = False
        self.page.dialog = None
        await self.page.update_async()

    def _collect_settings(self) -> InstrumentSettings:
        symbol = self.symbol_input.value.strip().upper()
        base_qty = float(self.quantity_input.value)
        trigger_price = float(self.trigger_price_input.value)
        trigger_direction = int(self.trigger_direction_select.value or 2)
        trigger_by = self.trigger_by_select.value or "LastPrice"
        tp1 = TakeProfitLevel(
            offset_percent=float(self.tp1_offset_input.value),
            quantity_percent=float(self.tp1_qty_input.value),
        )
        tp2 = TakeProfitLevel(
            offset_percent=float(self.tp2_offset_input.value),
            quantity_percent=float(self.tp2_qty_input.value),
        )
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
