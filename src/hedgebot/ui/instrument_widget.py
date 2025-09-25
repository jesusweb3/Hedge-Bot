# src/hedgebot/ui/instrument_widget.py
"""Instrument card implementation for the Flet UI."""
from __future__ import annotations

from typing import TYPE_CHECKING, List

import flet as ft

from ..config import InstrumentSettings, RefillConfig, StopLossLevel, TakeProfitLevel
from ..events import InstrumentEvent, LogEvent, OrdersEvent, StatusEvent
from ..state import InstrumentStatus, ManagedOrder

if TYPE_CHECKING:
    from .app import HedgeBotFletApp


class InstrumentCard:
    """Visual representation of a trading instrument."""

    def __init__(self, app: "HedgeBotFletApp", instrument_id: str, settings: InstrumentSettings, engine) -> None:
        self.app = app
        self.instrument_id = instrument_id
        self.settings = settings.clone()
        self.engine = engine

        self.title = ft.Text(f"Инструмент {self.settings.symbol}", weight=ft.FontWeight.BOLD, size=18)

        self.symbol_input = ft.TextField(label="Символ", value=self.settings.symbol.upper())
        self.quantity_input = ft.TextField(label="Базовый объём", value=str(self.settings.base_quantity))
        self.trigger_price_input = ft.TextField(label="Цена входа", value=str(self.settings.entry_trigger_price))
        self.trigger_direction_select = ft.Dropdown(
            label="Направление триггера",
            value=str(self.settings.entry_trigger_direction),
            options=[
                ft.dropdown.Option(key="1", text="Price >="),
                ft.dropdown.Option(key="2", text="Price <="),
            ],
        )
        self.trigger_by_select = ft.Dropdown(
            label="Триггер по",
            value=self.settings.trigger_by,
            options=[
                ft.dropdown.Option("LastPrice", "Last"),
                ft.dropdown.Option("MarkPrice", "Mark"),
                ft.dropdown.Option("IndexPrice", "Index"),
            ],
        )
        self.tp1_offset_input = ft.TextField(label="TP1 %", value=str(self.settings.take_profits[0].offset_percent))
        self.tp1_qty_input = ft.TextField(label="TP1 объём %", value=str(self.settings.take_profits[0].quantity_percent))
        self.tp2_offset_input = ft.TextField(label="TP2 %", value=str(self.settings.take_profits[1].offset_percent))
        self.tp2_qty_input = ft.TextField(label="TP2 объём %", value=str(self.settings.take_profits[1].quantity_percent))
        stops_default = ",".join(f"{sl.offset_percent}:{sl.quantity_percent}" for sl in self.settings.stop_losses)
        self.stop_pairs_input = ft.TextField(label="Стопы offset:qty", value=stops_default)
        self.refill_checkbox = ft.Checkbox(label="Доливка после TP1", value=self.settings.refill.enabled_after_tp1)
        self.refill_price_input = ft.TextField(label="Цена доливки %", value=str(self.settings.refill.price_offset_percent))
        self.refill_qty_input = ft.TextField(label="Объём доливки %", value=str(self.settings.refill.quantity_percent))
        self.settings_message = ft.Text(value="", color=ft.Colors.GREEN)

        self.status_label = ft.Text("Статус: CONFIGURED", weight=ft.FontWeight.BOLD)
        self.status_details = ft.Text("")
        self.start_button = ft.ElevatedButton("Старт", icon=ft.Icons.PLAY_ARROW, on_click=self._on_start)
        self.stop_button = ft.OutlinedButton("Стоп", icon=ft.Icons.STOP_CIRCLE, on_click=self._on_stop)
        self.close_button = ft.TextButton("Закрыть всё", icon=ft.Icons.CLOSE, on_click=self._on_close)
        self.remove_button = ft.TextButton("Удалить", icon=ft.Icons.DELETE, on_click=self._on_remove)

        self.orders_table = ft.DataTable(
            columns=[
                ft.DataColumn(label=ft.Text("ID")),
                ft.DataColumn(label=ft.Text("Тип")),
                ft.DataColumn(label=ft.Text("Сторона")),
                ft.DataColumn(label=ft.Text("Позиция")),
                ft.DataColumn(label=ft.Text("Кол-во")),
                ft.DataColumn(label=ft.Text("Цена")),
                ft.DataColumn(label=ft.Text("Триггер")),
                ft.DataColumn(label=ft.Text("RO")),
                ft.DataColumn(label=ft.Text("Статус")),
                ft.DataColumn(label=ft.Text("Обновлено")),
            ],
            rows=[],
        )
        self.log_list = ft.ListView(expand=1, spacing=4, auto_scroll=True, height=220)

        self.save_button = ft.FilledButton("Сохранить", icon=ft.Icons.SAVE, on_click=self._on_save)

        settings_tab = ft.Container(
            content=ft.Column(
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
                    self.settings_message,
                    self.save_button,
                ],
                tight=True,
                spacing=10,
            ),
        )

        status_tab = ft.Container(
            content=ft.Column(
                controls=[
                    self.status_label,
                    self.status_details,
                    ft.Row(
                        controls=[
                            self.start_button,
                            self.stop_button,
                            self.close_button,
                            self.remove_button,
                        ],
                        wrap=True,
                        spacing=10,
                    ),
                ],
                tight=True,
                spacing=10,
            ),
        )

        orders_tab = ft.Container(content=ft.Column([self.orders_table], tight=True))
        log_tab = ft.Container(content=ft.Column([self.log_list], tight=True))

        self.tabs = ft.Tabs(
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Настройки",
                    content=settings_tab
                ),
                ft.Tab(
                    text="Статус",
                    content=status_tab
                ),
                ft.Tab(
                    text="Ордеры",
                    content=orders_tab
                ),
                ft.Tab(
                    text="Лог",
                    content=log_tab
                ),
            ],
        )

        self.control = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    controls=[self.title, self.tabs],
                    spacing=12,
                ),
                padding=15,
            )
        )

        self._update_button_states(InstrumentStatus.CONFIGURED)

    async def handle_event(self, event: InstrumentEvent) -> None:
        if isinstance(event, StatusEvent):
            self._handle_status_event(event)
        elif isinstance(event, LogEvent):
            self._handle_log_event(event)
        elif isinstance(event, OrdersEvent):
            self._handle_orders_event(event)
        self.app.page.update()

    async def _on_start(self, _) -> None:
        await self.app.run_command(self.instrument_id, "start")

    async def _on_stop(self, _) -> None:
        await self.app.run_command(self.instrument_id, "stop")

    async def _on_close(self, _) -> None:
        await self.app.run_command(self.instrument_id, "close")

    async def _on_remove(self, _) -> None:
        await self.app.run_command(self.instrument_id, "remove")

    async def _on_save(self, _) -> None:
        try:
            settings = self._collect_settings_from_form()
        except Exception as exc:  # pylint: disable=broad-except
            self.settings_message.value = f"Ошибка: {exc}"
            self.settings_message.color = ft.Colors.RED
            self.app.page.update()
            return

        error = await self.app.run_command(self.instrument_id, "update", settings)
        if error:
            self.settings_message.value = f"Ошибка: {error}"
            self.settings_message.color = ft.Colors.RED
        else:
            self.settings = settings.clone()
            self.title.value = f"Инструмент {self.settings.symbol}"
            self.settings_message.value = "Настройки сохранены"
            self.settings_message.color = ft.Colors.GREEN
        self.app.page.update()

    def _collect_settings_from_form(self) -> InstrumentSettings:
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

    def _handle_status_event(self, event: StatusEvent) -> None:
        self.status_label.value = f"Статус: {event.status.value.upper()}"
        self.status_details.value = event.details or ""
        self._update_button_states(event.status)

    def _handle_log_event(self, event: LogEvent) -> None:
        timestamp = event.timestamp.strftime("%H:%M:%S")
        color_map = {
            "info": ft.Colors.GREEN,
            "warning": ft.Colors.AMBER,
            "error": ft.Colors.RED,
            "debug": ft.Colors.BLUE_GREY,
        }
        color = color_map.get(event.level, ft.Colors.WHITE)
        self.log_list.controls.append(ft.Text(f"[{timestamp}] {event.message}", color=color))
        while len(self.log_list.controls) > 500:
            self.log_list.controls.pop(0)

    def _handle_orders_event(self, event: OrdersEvent) -> None:
        rows = [
            ft.DataRow(
                cells=[ft.DataCell(content=ft.Text(value)) for value in self._order_to_row(order)]
            )
            for order in event.orders
        ]
        self.orders_table.rows = rows

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

    def _update_button_states(self, status: InstrumentStatus) -> None:
        self.start_button.disabled = status in {InstrumentStatus.WAITING_ENTRY, InstrumentStatus.ACTIVE}
        self.stop_button.disabled = status not in {InstrumentStatus.WAITING_ENTRY, InstrumentStatus.ACTIVE}
        self.close_button.disabled = status == InstrumentStatus.CONFIGURED
        self.remove_button.disabled = status in {InstrumentStatus.WAITING_ENTRY, InstrumentStatus.ACTIVE}