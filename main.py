"""FastAPI application exposing Hedg-Bot controls and UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from hedgbot.config import get_settings
from hedgbot.manager import BotManager, default_config
from hedgbot.models import InstrumentConfig, InstrumentState, ManagerState, OrderSide

app = FastAPI(title="Hedg-Bot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "hedgbot" / "app" / "templates"
STATIC_DIR = BASE_DIR / "hedgbot" / "app" / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Initialise configuration and bots
get_settings()  # ensure .env is parsed early
_default_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
manager = BotManager(default_config(symbol) for symbol in _default_symbols)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the control panel."""

    state = manager.snapshot()
    return templates.TemplateResponse(
        "index.html", {"request": request, "state": state}
    )


@app.get("/api/instruments", response_model=ManagerState)
async def get_instruments() -> ManagerState:
    return manager.snapshot()


@app.get("/api/instruments/{symbol}", response_model=InstrumentState)
async def get_instrument(symbol: str) -> InstrumentState:
    try:
        return manager.get_bot(symbol).snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/instruments/{symbol}/config", response_model=InstrumentState)
async def update_config(symbol: str, payload: InstrumentConfig) -> InstrumentState:
    if payload.symbol != symbol:
        raise HTTPException(
            status_code=400,
            detail="Symbol in payload does not match URL",
        )
    try:
        await manager.update_config(symbol, payload)
        return manager.get_bot(symbol).snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/instruments/{symbol}/start", response_model=InstrumentState)
async def start_bot(symbol: str) -> InstrumentState:
    try:
        await manager.start(symbol)
        return manager.get_bot(symbol).snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/instruments/{symbol}/stop", response_model=InstrumentState)
async def stop_bot(symbol: str) -> InstrumentState:
    try:
        await manager.stop(symbol)
        return manager.get_bot(symbol).snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/instruments/{symbol}/close", response_model=InstrumentState)
async def close_bot(symbol: str) -> InstrumentState:
    try:
        await manager.close(symbol)
        return manager.get_bot(symbol).snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/instruments/start_all", response_model=ManagerState)
async def start_all() -> ManagerState:
    await manager.start_all()
    return manager.snapshot()


@app.post("/api/instruments/stop_all", response_model=ManagerState)
async def stop_all() -> ManagerState:
    await manager.stop_all()
    return manager.snapshot()


@app.post("/api/instruments/{symbol}/simulate/tp/{level}", response_model=InstrumentState)
async def simulate_tp(
    symbol: str,
    level: int,
    side: OrderSide = Body(..., embed=True, description="Side to simulate"),
) -> InstrumentState:
    try:
        bot = manager.get_bot(symbol)
        await bot.trigger_take_profit(side, level)
        return bot.snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IndexError:
        raise HTTPException(status_code=400, detail="Invalid TP level index")


@app.post("/api/instruments/{symbol}/simulate/sl/{level}", response_model=InstrumentState)
async def simulate_sl(
    symbol: str,
    level: int,
    side: OrderSide = Body(..., embed=True, description="Side to simulate"),
) -> InstrumentState:
    try:
        bot = manager.get_bot(symbol)
        await bot.trigger_stop_loss(side, level)
        return bot.snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IndexError:
        raise HTTPException(status_code=400, detail="Invalid SL level index")


@app.post("/api/instruments/{symbol}/simulate/dca", response_model=InstrumentState)
async def simulate_dca_fill(
    symbol: str,
    order_id: str = Body(..., embed=True, description="DCA order identifier"),
) -> InstrumentState:
    try:
        bot = manager.get_bot(symbol)
        await bot.trigger_dca_fill(order_id)
        return bot.snapshot()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
async def healthcheck() -> dict[str, Any]:
    return {"status": "ok"}


__all__ = ["app"]
