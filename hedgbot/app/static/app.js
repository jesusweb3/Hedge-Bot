const API = {
  async request(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      const message = detail.detail || response.statusText || "Ошибка запроса";
      throw new Error(message);
    }
    if (response.status === 204) {
      return null;
    }
    return response.json();
  },

  listInstruments() {
    return this.request("/api/instruments");
  },

  updateConfig(symbol, payload) {
    return this.request(`/api/instruments/${symbol}/config`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  start(symbol) {
    return this.request(`/api/instruments/${symbol}/start`, { method: "POST" });
  },

  stop(symbol) {
    return this.request(`/api/instruments/${symbol}/stop`, { method: "POST" });
  },

  close(symbol) {
    return this.request(`/api/instruments/${symbol}/close`, { method: "POST" });
  },

  startAll() {
    return this.request(`/api/instruments/start_all`, { method: "POST" });
  },

  stopAll() {
    return this.request(`/api/instruments/stop_all`, { method: "POST" });
  },

  refreshInstrument(symbol) {
    return this.request(`/api/instruments/${symbol}`);
  },
};

function setupTabs(card) {
  const buttons = card.querySelectorAll(".tab-button");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      const target = button.dataset.target;
      card
        .querySelectorAll(".tab-content")
        .forEach((section) => section.classList.remove("active"));
      card
        .querySelector(`.tab-content[data-tab="${target}"]`)
        .classList.add("active");
    });
  });
}

function createStopLossRow(offset = "", volume = "") {
  const row = document.createElement("div");
  row.className = "stop-loss-row";
  row.innerHTML = `
    <label>
      Отступ (%):
      <input type="number" step="0.01" name="sl-offset" value="${offset}" required />
    </label>
    <label>
      Объём (%):
      <input type="number" step="0.01" name="sl-volume" value="${volume}" required />
    </label>
    <button type="button" class="remove-stop">×</button>
  `;
  row.querySelector(".remove-stop").addEventListener("click", () => {
    row.remove();
  });
  return row;
}

function collectStopLosses(container) {
  return Array.from(container.querySelectorAll(".stop-loss-row")).map((row) => ({
    offset_percent: parseFloat(row.querySelector('input[name="sl-offset"]').value),
    volume_percent: parseFloat(row.querySelector('input[name="sl-volume"]').value),
  }));
}

function renderStopLosses(container, stopLosses) {
  container.innerHTML = "";
  stopLosses.forEach((sl) => {
    container.appendChild(createStopLossRow(sl.offset_percent, sl.volume_percent));
  });
}

function collectConfig(card) {
  const form = card.querySelector(".config-form");
  const symbol = card.dataset.symbol;
  const entryAmount = parseFloat(form.querySelector('input[name="entry_amount"]').value);
  const tpRows = Array.from(form.querySelectorAll(".tp-row"));
  const takeProfits = tpRows.map((row) => ({
    label: row.dataset.label,
    offset_percent: parseFloat(row.querySelector('input[name="tp-offset"]').value),
    volume_percent: parseFloat(row.querySelector('input[name="tp-volume"]').value),
  }));

  const stopLossContainer = form.querySelector(".stop-loss-list");
  const stopLosses = collectStopLosses(stopLossContainer);

  const dcaEnabled = form.querySelector('input[name="dca-enabled"]').checked;
  const dcaOffsetValue = form.querySelector('input[name="dca-offset"]').value.trim();
  const dcaQuantityValue = form.querySelector('input[name="dca-quantity"]').value.trim();

  if (dcaEnabled && (!dcaOffsetValue || !dcaQuantityValue)) {
    throw new Error("Для включенной доливки необходимо указать отступ и объём");
  }

  const tp1Dca = {
    enabled: dcaEnabled,
    offset_percent: dcaOffsetValue ? parseFloat(dcaOffsetValue) : null,
    quantity: dcaQuantityValue ? parseFloat(dcaQuantityValue) : null,
  };

  return {
    symbol,
    entry_amount: entryAmount,
    take_profits: takeProfits,
    stop_losses: stopLosses,
    tp1_dca: tp1Dca,
  };
}

function renderInstrument(card, data) {
  card
    .querySelector('input[name="entry_amount"]')
    .value = data.config.entry_amount;
  const tpRows = card.querySelectorAll(".tp-row");
  tpRows.forEach((row, index) => {
    const tp = data.config.take_profits[index];
    row.querySelector('input[name="tp-offset"]').value = tp.offset_percent;
    row.querySelector('input[name="tp-volume"]').value = tp.volume_percent;
  });

  const stopLossContainer = card.querySelector(".stop-loss-list");
  renderStopLosses(stopLossContainer, data.config.stop_losses);

  const dcaEnabled = card.querySelector('input[name="dca-enabled"]');
  dcaEnabled.checked = data.config.tp1_dca.enabled;
  card.querySelector('input[name="dca-offset"]').value =
    data.config.tp1_dca.offset_percent ?? "";
  card.querySelector('input[name="dca-quantity"]').value =
    data.config.tp1_dca.quantity ?? "";

  const statusIndicator = card.querySelector(".status-indicator");
  statusIndicator.dataset.running = data.is_running ? "true" : "false";
  statusIndicator.textContent = data.is_running ? "Работает" : "Остановлен";
  card.querySelector(".status-text").textContent = data.is_running
    ? "Работает"
    : "Остановлен";

  const longPosition = Number(data.positions.LONG ?? 0);
  const shortPosition = Number(data.positions.SHORT ?? 0);
  card.querySelector('[data-position="LONG"]').textContent = longPosition.toFixed(2);
  card.querySelector('[data-position="SHORT"]').textContent = shortPosition.toFixed(2);

  const ordersTable = card.querySelector(".open-orders tbody");
  if (ordersTable) {
    ordersTable.innerHTML = data.open_orders
      .map(
        (order) => `
        <tr>
          <td>${order.id}</td>
          <td>${order.type}</td>
          <td>${order.side}</td>
          <td>${Number(order.quantity ?? 0).toFixed(2)}</td>
          <td>${order.status}</td>
        </tr>
      `
      )
      .join("");
  }

  const dcaTable = card.querySelector(".dca-table tbody");
  if (dcaTable) {
    dcaTable.innerHTML = data.dca_orders
      .map(
        (order) => `
        <tr>
          <td>${order.id}</td>
          <td>${order.side}</td>
          <td>${Number(order.quantity ?? 0).toFixed(2)}</td>
          <td>${order.status}</td>
        </tr>
      `
      )
      .join("");
  }

  const logList = card.querySelector(".log-list ul");
  if (logList) {
    logList.innerHTML = data.logs
      .slice()
      .reverse()
      .map(
        (entry) => `
        <li>
          <time>${new Date(entry.timestamp).toLocaleString()}</time>
          <span class="level level-${entry.level.toLowerCase()}">${entry.level}</span>
          <span class="message">${entry.message}</span>
        </li>
      `
      )
      .join("");
  }
}

function setupConfigForm(card) {
  const form = card.querySelector(".config-form");
  const stopLossContainer = form.querySelector(".stop-loss-list");
  const addStopButton = form.querySelector(".add-stop");

  addStopButton.addEventListener("click", () => {
    if (stopLossContainer.children.length >= 10) {
      alert("Можно задать не более 10 стоп-лоссов");
      return;
    }
    stopLossContainer.appendChild(createStopLossRow());
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const symbol = card.dataset.symbol;
    try {
      const config = collectConfig(card);
      const data = await API.updateConfig(symbol, config);
      renderInstrument(card, data);
      alert("Настройки обновлены");
    } catch (error) {
      alert(error.message);
    }
  });
}

function setupStatusActions(card) {
  const symbol = card.dataset.symbol;
  const startButton = card.querySelector(".status-actions .start");
  const stopButton = card.querySelector(".status-actions .stop");
  const closeButton = card.querySelector(".status-actions .close");

  startButton.addEventListener("click", async () => {
    try {
      const data = await API.start(symbol);
      renderInstrument(card, data);
    } catch (error) {
      alert(error.message);
    }
  });

  stopButton.addEventListener("click", async () => {
    try {
      const data = await API.stop(symbol);
      renderInstrument(card, data);
    } catch (error) {
      alert(error.message);
    }
  });

  closeButton.addEventListener("click", async () => {
    if (!confirm("Закрыть позицию и отменить ордера?")) {
      return;
    }
    try {
      const data = await API.close(symbol);
      renderInstrument(card, data);
    } catch (error) {
      alert(error.message);
    }
  });
}

function setupLogRefresh(card) {
  const refreshButton = card.querySelector(".log-list .refresh");
  const symbol = card.dataset.symbol;
  if (!refreshButton) return;
  refreshButton.addEventListener("click", async () => {
    try {
      const data = await API.refreshInstrument(symbol);
      renderInstrument(card, data);
    } catch (error) {
      alert(error.message);
    }
  });
}

function initGlobalControls() {
  const startAll = document.getElementById("start-all");
  const stopAll = document.getElementById("stop-all");

  startAll.addEventListener("click", async () => {
    try {
      const state = await API.startAll();
      updateAll(state);
    } catch (error) {
      alert(error.message);
    }
  });

  stopAll.addEventListener("click", async () => {
    try {
      const state = await API.stopAll();
      updateAll(state);
    } catch (error) {
      alert(error.message);
    }
  });
}

function updateAll(managerState) {
  managerState.instruments.forEach((instrument) => {
    const card = document.querySelector(`.instrument-card[data-symbol="${instrument.symbol}"]`);
    if (card) {
      renderInstrument(card, instrument);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".instrument-card").forEach((card) => {
    setupTabs(card);
    setupConfigForm(card);
    setupStatusActions(card);
    setupLogRefresh(card);
  });
  initGlobalControls();
});
