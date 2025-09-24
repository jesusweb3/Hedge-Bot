# order_monitor_websocket.py
# -*- coding: utf-8 -*-
"""
Мониторинг исполненных ордеров через приватный WebSocket (Bybit V5).
- Подключается к приватному WebSocket каналу 'order'
- Фильтрует только исполненные ордеры (orderStatus="Filled") по конкретным Order IDs
- Логирует информацию об исполненных ордерах для указанного символа
- Ключи читаются из .env
"""

import os
import sys
import json
import time
import hmac
import hashlib
from datetime import datetime
from dotenv import load_dotenv
import websocket

# 🔧 Параметры мониторинга
SYMBOL = "BTCUSDT"  # Символ для мониторинга
ORDER_IDS = ["32bc732f-9064-4750-83f7-924d9bb3f1d2"]  # Список Order ID для отслеживания


class OrderMonitor:
    def __init__(self, symbol: str, order_ids: list[str]):
        load_dotenv()
        self.symbol = symbol
        self.order_ids = set(order_ids)  # Используем set для быстрого поиска
        self.filled_orders = set()  # Отслеживаем уже исполненные ордеры
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")
        self.testnet = self._str_to_bool(os.getenv("BYBIT_TESTNET"))

        if not self.api_key or not self.api_secret:
            raise RuntimeError("Нет ключей BYBIT_API_KEY/BYBIT_API_SECRET в .env")

        if not self.order_ids:
            raise ValueError("Список order_ids не может быть пустым")

        self.ws_url = "wss://stream-testnet.bybit.com/v5/private" if self.testnet else "wss://stream.bybit.com/v5/private"
        self.ws = None

        print(
            f"[{self._get_timestamp()}] Инициализация мониторинга для {len(self.order_ids)} ордеров: {list(self.order_ids)}")

    @staticmethod
    def _str_to_bool(v: str | None) -> bool:
        return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    def _generate_signature(self, expires: int) -> str:
        """Генерация подписи для аутентификации WebSocket"""
        param_str = f'GET/realtime{expires}'
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _on_open(self, ws):
        """Обработчик открытия WebSocket соединения"""
        print(f"[{self._get_timestamp()}] WebSocket соединение установлено")

        # Аутентификация
        expires = int((time.time() + 10) * 1000)
        signature = self._generate_signature(expires)

        auth_message = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }

        ws.send(json.dumps(auth_message))
        print(f"[{self._get_timestamp()}] Отправлена аутентификация")

    def _on_message(self, ws, message):
        """Обработчик сообщений WebSocket"""
        try:
            data = json.loads(message)

            # Проверяем успешную аутентификацию
            if data.get("op") == "auth" and data.get("success"):
                print(f"[{self._get_timestamp()}] Аутентификация успешна")

                # Подписываемся на канал order
                subscribe_message = {
                    "op": "subscribe",
                    "args": ["order"]
                }
                ws.send(json.dumps(subscribe_message))
                print(f"[{self._get_timestamp()}] Подписка на канал 'order' отправлена")
                return

            # Подтверждение подписки
            if data.get("op") == "subscribe" and data.get("success"):
                print(f"[{self._get_timestamp()}] Успешная подписка на канал 'order'")
                print(f"[{self._get_timestamp()}] Мониторинг ордеров для {self.symbol} запущен...")
                print(f"[{self._get_timestamp()}] Отслеживаемые Order IDs: {list(self.order_ids)}")
                return

            # Обработка данных ордеров
            if data.get("topic") == "order" and "data" in data:
                self._process_order_data(data["data"])

        except json.JSONDecodeError as e:
            print(f"[{self._get_timestamp()}] Ошибка парсинга JSON: {e}")
        except Exception as e:
            print(f"[{self._get_timestamp()}] Ошибка обработки сообщения: {e}")

    def _process_order_data(self, orders_data):
        """Обработка данных ордеров"""
        for order in orders_data:
            symbol = order.get("symbol", "")
            order_id = order.get("orderId", "")
            order_status = order.get("orderStatus", "")

            # Фильтруем только нужный символ, отслеживаемые ордеры и исполненные статусы
            if (symbol == self.symbol and
                    order_id in self.order_ids and
                    order_status == "Filled" and
                    order_id not in self.filled_orders):

                self._log_filled_order(order)
                self.filled_orders.add(order_id)

                # Проверяем, все ли ордеры исполнены
                if len(self.filled_orders) == len(self.order_ids):
                    print(f"\n[{self._get_timestamp()}] 🎉 ВСЕ ОТСЛЕЖИВАЕМЫЕ ОРДЕРЫ ИСПОЛНЕНЫ!")
                    print(
                        f"[{self._get_timestamp()}] Исполнено: {len(self.filled_orders)}/{len(self.order_ids)} ордеров")
                    print(f"[{self._get_timestamp()}] Завершение мониторинга...")
                    self.ws.close()

    def _log_filled_order(self, order):
        """Логирование исполненного ордера"""
        order_id = order.get("orderId", "N/A")
        order_link_id = order.get("orderLinkId", "N/A")
        side = order.get("side", "N/A")
        order_type = order.get("orderType", "N/A")
        qty = order.get("qty", "0")
        price = order.get("avgPrice", order.get("price", "0"))
        cumulative_qty = order.get("cumExecQty", "0")

        timestamp = self._get_timestamp()
        remaining = len(self.order_ids) - len(self.filled_orders) - 1

        log_message = (
            f"[{timestamp}] ✅ ORDER FILLED: {self.symbol} | "
            f"ID: {order_id} | LinkID: {order_link_id} | "
            f"Type: {order_type} | Side: {side} | "
            f"Qty: {qty} | Executed: {cumulative_qty} | "
            f"Price: {price} | Осталось: {remaining}"
        )

        print(log_message)

    def _on_error(self, _, error):
        """Обработчик ошибок WebSocket"""
        print(f"[{self._get_timestamp()}] WebSocket ошибка: {error}")

    def _on_close(self, _, close_status_code, close_msg):
        """Обработчик закрытия WebSocket соединения"""
        print(
            f"[{self._get_timestamp()}] WebSocket соединение закрыто. Код: {close_status_code}, Сообщение: {close_msg}")

    @staticmethod
    def _get_timestamp() -> str:
        """Получение текущего времени в читаемом формате"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def start_monitoring(self):
        """Запуск мониторинга ордеров"""
        print(f"[{self._get_timestamp()}] Запуск мониторинга ордеров для {self.symbol}")
        print(f"[{self._get_timestamp()}] Подключение к {'TESTNET' if self.testnet else 'MAINNET'}")

        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        try:
            self.ws.run_forever()
        except KeyboardInterrupt:
            print(f"\n[{self._get_timestamp()}] Мониторинг остановлен пользователем")
        except Exception as e:
            print(f"[{self._get_timestamp()}] Критическая ошибка: {e}")
            sys.exit(1)


def main():
    try:
        monitor = OrderMonitor(SYMBOL, ORDER_IDS)
        monitor.start_monitoring()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()