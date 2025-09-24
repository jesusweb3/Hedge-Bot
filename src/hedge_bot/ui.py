"""Textual user interface components for Hedge-Bot."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Log,
    Static,
    TabbedContent,
    TabPane,
)

from .config import (
    InstrumentConfig,
    RefillConfig,
    SideConfig,
    StopLossConfig,
    TakeProfitConfig,
)
from .engine import HedgeBotEngine, ManagedInstrument
from .state import InstrumentState, InstrumentStatus


def _parse_decimal(value: str, *, name: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Некорректное число в поле '{name}': {value}") from exc


def _parse_stop_levels(raw: str, side: str) -> list[StopLossConfig]:
    raw = raw.strip()
    if not raw:
        return []
    levels: list[StopLossConfig] = []
    for chunk in raw.split(","):
        if ":" not in chunk:
            raise ValueError(
                "Стоп-лосс должен быть в формате 'цена:процент', например 110000:25"
            )
        price_str, pct_str = chunk.split(":", 1)
        levels.append(
            StopLossConfig(
                trigger_price=_parse_decimal(price_str, name=f"SL {side}"),
                quantity_pct=_parse_decimal(pct_str, name=f"SL {side}"),
            )
        )
    return levels


@dataclass
class FormData:
    symbol: str
    entry_price: Decimal
    entry_usdt: Decimal
    long_tp1_price: Decimal
    long_tp1_pct: Decimal
    long_tp2_price: Decimal
    long_tp2_pct: Decimal
    short_tp1_price: Decimal
    short_tp1_pct: Decimal
    short_tp2_price: Decimal
    short_tp2_pct: Decimal
    long_stops: str
    short_stops: str
    refill_enabled: bool
    refill_price: str
    refill_quantity: str


class InstrumentForm(Static):
    """Popup form allowing the user to configure a new instrument."""

    class Submitted(Message):
        def __init__(self, sender: "InstrumentForm", config: InstrumentConfig) -> None:
            super().__init__(sender)
            self.config = config

    DEFAULT_CSS = """
    InstrumentForm {
        background: $surface;
        color: $text;
        padding: 2 4;
        border: tall $accent;
        width: 60%;
        height: auto;
    }
    InstrumentForm .form-title {
        text-style: bold;
        margin-bottom: 1;
    }
    InstrumentForm Input, InstrumentForm Checkbox {
        margin: 0 0 1 0;
    }
    InstrumentForm .form-actions {
        align-horizontal: right;
        margin-top: 2;
        gap: 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.display = False

    def compose(self) -> ComposeResult:
        yield Label("Добавить инструмент", classes="form-title")
        yield Input(placeholder="Например BTCUSDT", id="symbol")
        yield Input(placeholder="Цена входа", id="entry_price")
        yield Input(placeholder="Объём в USDT", id="entry_usdt")
        yield Label("Тейк-профиты LONG (цена / процент)")
        yield Horizontal(
            Input(placeholder="TP1 цена", id="long_tp1_price"),
            Input(placeholder="TP1 %", id="long_tp1_pct"),
            classes="row",
        )
        yield Horizontal(
            Input(placeholder="TP2 цена", id="long_tp2_price"),
            Input(placeholder="TP2 %", id="long_tp2_pct"),
            classes="row",
        )
        yield Label("Тейк-профиты SHORT (цена / процент)")
        yield Horizontal(
            Input(placeholder="TP1 цена", id="short_tp1_price"),
            Input(placeholder="TP1 %", id="short_tp1_pct"),
            classes="row",
        )
        yield Horizontal(
            Input(placeholder="TP2 цена", id="short_tp2_price"),
            Input(placeholder="TP2 %", id="short_tp2_pct"),
            classes="row",
        )
        yield Input(
            placeholder="Стопы LONG, формат цена:процент,...", id="long_stops"
        )
        yield Input(
            placeholder="Стопы SHORT, формат цена:процент,...", id="short_stops"
        )
        yield Checkbox(label="Использовать доливку после TP1", id="refill_enabled")
        yield Input(placeholder="Цена доливки", id="refill_price")
        yield Input(placeholder="Объём доливки в USDT", id="refill_quantity")
        yield Horizontal(
            Button("Добавить", id="submit", variant="primary"),
            Button("Отмена", id="cancel"),
            classes="form-actions",
        )

    def show(self) -> None:
        self.display = True
        self.refresh()

    def hide(self) -> None:
        self.display = False
        self._reset_fields()
        self.refresh()

    def _reset_fields(self) -> None:
        for input_id in [
            "symbol",
            "entry_price",
            "entry_usdt",
            "long_tp1_price",
            "long_tp1_pct",
            "long_tp2_price",
            "long_tp2_pct",
            "short_tp1_price",
            "short_tp1_pct",
            "short_tp2_price",
            "short_tp2_pct",
            "long_stops",
            "short_stops",
            "refill_price",
            "refill_quantity",
        ]:
            self.query_one(f"#{input_id}", Input).value = ""
        self.query_one("#refill_enabled", Checkbox).value = False

    def _gather(self) -> FormData:
        def _value(widget_id: str) -> str:
            return self.query_one(f"#{widget_id}", Input).value or ""

        return FormData(
            symbol=_value("symbol"),
            entry_price=_parse_decimal(_value("entry_price"), name="Цена входа"),
            entry_usdt=_parse_decimal(_value("entry_usdt"), name="Объём"),
            long_tp1_price=_parse_decimal(_value("long_tp1_price"), name="Long TP1 цена"),
            long_tp1_pct=_parse_decimal(_value("long_tp1_pct"), name="Long TP1 %"),
            long_tp2_price=_parse_decimal(_value("long_tp2_price"), name="Long TP2 цена"),
            long_tp2_pct=_parse_decimal(_value("long_tp2_pct"), name="Long TP2 %"),
            short_tp1_price=_parse_decimal(_value("short_tp1_price"), name="Short TP1 цена"),
            short_tp1_pct=_parse_decimal(_value("short_tp1_pct"), name="Short TP1 %"),
            short_tp2_price=_parse_decimal(_value("short_tp2_price"), name="Short TP2 цена"),
            short_tp2_pct=_parse_decimal(_value("short_tp2_pct"), name="Short TP2 %"),
            long_stops=_value("long_stops"),
            short_stops=_value("short_stops"),
            refill_enabled=self.query_one("#refill_enabled", Checkbox).value,
            refill_price=_value("refill_price"),
            refill_quantity=_value("refill_quantity"),
        )

    def _build_config(self, data: FormData) -> InstrumentConfig:
        long_config = SideConfig(
            take_profits=[
                TakeProfitConfig(price=data.long_tp1_price, quantity_pct=data.long_tp1_pct),
                TakeProfitConfig(price=data.long_tp2_price, quantity_pct=data.long_tp2_pct),
            ],
            stop_losses=_parse_stop_levels(data.long_stops, "long"),
        )
        short_config = SideConfig(
            take_profits=[
                TakeProfitConfig(price=data.short_tp1_price, quantity_pct=data.short_tp1_pct),
                TakeProfitConfig(price=data.short_tp2_price, quantity_pct=data.short_tp2_pct),
            ],
            stop_losses=_parse_stop_levels(data.short_stops, "short"),
        )
        refill_cfg = RefillConfig(
            enabled=data.refill_enabled,
            price=_parse_decimal(data.refill_price, name="Цена доливки") if data.refill_enabled else None,
            quantity=_parse_decimal(data.refill_quantity, name="Объём доливки") if data.refill_enabled else None,
        )
        return InstrumentConfig(
            symbol=data.symbol,
            entry_trigger_price=data.entry_price,
            entry_quantity_usdt=data.entry_usdt,
            long=long_config,
            short=short_config,
            refill_after_tp1=refill_cfg,
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.hide()
            event.stop()
        elif event.button.id == "submit":
            try:
                data = self._gather()
                config = self._build_config(data)
            except Exception as exc:  # noqa: BLE001
                self.app.bell()
                self.app.notify(str(exc), severity="error")
                return
            self.hide()
            await self.emit(self.Submitted(self, config))


class InstrumentItem(ListItem):
    """Representation of a single instrument in the sidebar list."""

    def __init__(self, symbol: str) -> None:
        super().__init__()
        self.symbol = symbol
        self._status_label: Label | None = None

    def compose(self) -> ComposeResult:
        status = Label(InstrumentStatus.IDLE.value, classes="status")
        self._status_label = status
        yield Horizontal(
            Label(self.symbol, classes="symbol"),
            Static(classes="spacer"),
            status,
        )

    def update_status(self, state: InstrumentState) -> None:
        if self._status_label:
            self._status_label.update(state.status.value)
        if state.status is InstrumentStatus.ERROR:
            self.add_class("error")
        else:
            self.remove_class("error")


class InstrumentDetail(Static):
    """Displays state and controls for the selected instrument."""

    DEFAULT_CSS = """
    InstrumentDetail {
        padding: 2 3;
        color: $text;
    }
    InstrumentDetail .title {
        text-style: bold;
        font-size: 2;
        margin-bottom: 1;
    }
    InstrumentDetail .actions {
        gap: 1;
        margin-bottom: 1;
    }
    InstrumentDetail TabbedContent {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Выберите инструмент", classes="title", id="detail-title")
        yield Horizontal(
            Button("Запустить", id="detail-start", variant="success"),
            Button("Остановить", id="detail-stop", variant="warning"),
            Button("Удалить", id="detail-remove", variant="error"),
            classes="actions",
        )
        with TabbedContent():
            with TabPane("Настройки"):
                yield Static(id="detail-settings")
            with TabPane("Статус"):
                yield Static(id="detail-status")
            with TabPane("Ордеры"):
                table = DataTable(id="detail-orders")
                table.add_columns("ID", "Тип", "Сторона", "Qty", "Цена", "Состояние")
                yield table
            with TabPane("Лог"):
                yield Log(id="detail-log", highlight=True)

    def update_content(self, managed: Optional[ManagedInstrument]) -> None:
        title = self.query_one("#detail-title", Label)
        settings = self.query_one("#detail-settings", Static)
        status = self.query_one("#detail-status", Static)
        table = self.query_one("#detail-orders", DataTable)
        log_widget = self.query_one("#detail-log", Log)
        if not managed:
            title.update("Выберите инструмент")
            settings.update("Нет данных")
            status.update("")
            table.clear()
            log_widget.clear()
            return
        title.update(managed.symbol)
        cfg = managed.config
        settings.update(
            "\n".join(
                [
                    f"Символ: {cfg.symbol}",
                    f"Триггер входа: {cfg.entry_trigger_price}",
                    f"Объём входа: {cfg.entry_quantity_usdt} USDT",
                    "LONG TP: "
                    f"{cfg.long.take_profits[0].price}/{cfg.long.take_profits[0].quantity_pct}% , "
                    f"{cfg.long.take_profits[1].price}/{cfg.long.take_profits[1].quantity_pct}%",
                    "SHORT TP: "
                    f"{cfg.short.take_profits[0].price}/{cfg.short.take_profits[0].quantity_pct}% , "
                    f"{cfg.short.take_profits[1].price}/{cfg.short.take_profits[1].quantity_pct}%",
                    f"Доливка: {'включена' if cfg.refill_after_tp1.enabled else 'выкл.'}",
                ]
            )
        )
        state = managed.controller.state
        status.update(
            "\n".join(
                [
                    f"Статус: {state.status.value}",
                    f"Лонг позиция: {state.long_position_size}",
                    f"Шорт позиция: {state.short_position_size}",
                    f"Ордеров активно: {len(state.orders)}",
                    f"Последняя ошибка: {state.last_error or '-'}",
                ]
            )
        )
        table.clear()
        for order in state.orders.values():
            table.add_row(
                order.order_id,
                order.order_type.value,
                order.position_side,
                f"{order.qty:.4f}",
                "-" if order.price is None else f"{order.price:.2f}",
                "Filled" if order.filled_at else "Active",
            )
        log_widget.clear()
        for line in state.activity_log[-100:]:
            log_widget.write(line)


class HedgeBotApp(App):
    """Main textual application class."""

    CSS = """
    #app {
        background: #1f1f23;
    }
    .sidebar {
        background: #2b2b30;
        color: #fafafa;
        width: 30%;
        min-width: 32;
        padding: 2;
        border-right: tall #3c3c43;
    }
    .sidebar .title {
        text-style: bold;
        font-size: 2;
        margin-bottom: 2;
    }
    .sidebar ListView {
        height: 1fr;
        margin-bottom: 1;
    }
    .sidebar Button {
        margin-top: 1;
    }
    InstrumentDetail {
        width: 70%;
    }
    InstrumentItem Horizontal {
        width: 1fr;
        align: center middle;
    }
    InstrumentItem .spacer {
        width: 1fr;
    }
    InstrumentItem .status {
        color: #f4a259;
    }
    InstrumentItem.error {
        color: red;
    }
    """

    BINDINGS = [
        Binding("a", "show_form", "Добавить инструмент"),
        Binding("s", "start_selected", "Запустить"),
        Binding("x", "stop_selected", "Остановить"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.engine = HedgeBotEngine()
        self.selected_symbol: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header(name="Hedge-Bot")
        yield Footer()
        self.form = InstrumentForm()
        yield self.form
        with Horizontal(id="layout"):
            with Vertical(classes="sidebar"):
                yield Label("Hedge-Bot", classes="title")
                yield ListView(id="instrument-list")
                yield Button("Добавить инструмент", id="add-instrument", variant="primary")
                yield Button("Запустить все", id="start-all", variant="success")
                yield Button("Остановить все", id="stop-all", variant="warning")
            yield InstrumentDetail(id="instrument-detail")

    async def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh_state)

    async def _refresh_state(self) -> None:
        list_view = self.query_one("#instrument-list", ListView)
        detail = self.query_one("#instrument-detail", InstrumentDetail)
        for item in list_view.children:
            if isinstance(item, InstrumentItem):
                state = self.engine.get_state(item.symbol)
                if state:
                    item.update_status(state)
        if self.selected_symbol:
            managed = next((inst for inst in self.engine.get_instruments() if inst.symbol == self.selected_symbol), None)
            detail.update_content(managed)
        else:
            detail.update_content(None)

    async def action_show_form(self) -> None:
        self.form.show()

    async def action_start_selected(self) -> None:
        if self.selected_symbol:
            await self._run_with_feedback(
                self.engine.start_instrument(self.selected_symbol),
                f"Запуск {self.selected_symbol}",
            )

    async def action_stop_selected(self) -> None:
        if self.selected_symbol:
            await self._run_with_feedback(
                self.engine.stop_instrument(self.selected_symbol),
                f"Остановка {self.selected_symbol}",
            )

    async def _run_with_feedback(self, coro, success_message: str | None = None) -> bool:
        try:
            await coro
        except Exception as exc:  # noqa: BLE001
            self.bell()
            self.notify(str(exc), severity="error")
            return False
        if success_message:
            self.notify(success_message)
        return True

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-instrument":
            self.form.show()
        elif event.button.id == "start-all":
            await self._run_with_feedback(self.engine.start_all(), "Все инструменты запущены")
        elif event.button.id == "stop-all":
            await self._run_with_feedback(self.engine.stop_all(), "Все инструменты остановлены")
        elif event.button.id == "detail-start" and self.selected_symbol:
            await self._run_with_feedback(
                self.engine.start_instrument(self.selected_symbol),
                f"Запуск {self.selected_symbol}",
            )
        elif event.button.id == "detail-stop" and self.selected_symbol:
            await self._run_with_feedback(
                self.engine.stop_instrument(self.selected_symbol),
                f"Остановка {self.selected_symbol}",
            )
        elif event.button.id == "detail-remove" and self.selected_symbol:
            symbol = self.selected_symbol
            if await self._run_with_feedback(self.engine.remove_instrument(symbol)):
                self.selected_symbol = None
                await self._refresh_list()
                self.query_one("#instrument-detail", InstrumentDetail).update_content(None)
                self.notify(f"Инструмент {symbol} удалён")

    async def _refresh_list(self) -> None:
        list_view = self.query_one("#instrument-list", ListView)
        current = self.selected_symbol
        list_view.clear()
        for inst in self.engine.get_instruments():
            item = InstrumentItem(inst.symbol)
            list_view.append(item)
            if current and inst.symbol == current:
                list_view.index = len(list_view.children) - 1

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, InstrumentItem):
            self.selected_symbol = event.item.symbol
            detail = self.query_one("#instrument-detail", InstrumentDetail)
            managed = next((inst for inst in self.engine.get_instruments() if inst.symbol == self.selected_symbol), None)
            detail.update_content(managed)

    async def handle_instrument_form_submitted(self, message: InstrumentForm.Submitted) -> None:
        await self.engine.add_instrument(message.config)
        self.selected_symbol = message.config.symbol
        await self._refresh_list()
        detail = self.query_one("#instrument-detail", InstrumentDetail)
        managed = next((inst for inst in self.engine.get_instruments() if inst.symbol == self.selected_symbol), None)
        detail.update_content(managed)
        self.notify(f"Инструмент {message.config.symbol} добавлен")


def run_app() -> None:
    HedgeBotApp().run()
