"""Pydantic models for the SPEC §4 / §5 request bodies (shapes exactly as the contract)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .portfolio import canonical_mode

RUNGS = ("INCUBATION", "PROVING", "FULL")
TRIBES = ("Consistency", "Growth")


class TokenRequest(BaseModel):
    api_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600


class BarIn(BaseModel):
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class DataImportRequest(BaseModel):
    symbol: str
    timeframe: str = "M1"
    bars: list[BarIn] | None = None
    csv: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> "DataImportRequest":
        if (self.bars is None) == (self.csv is None):
            raise ValueError("provide exactly one of bars or csv")
        return self


class GatesIn(BaseModel):
    random_beat_pct: float = Field(95.0, ge=50, le=100)
    shuffle_n: int = Field(1000, ge=10, le=1000)
    max_dd_pct: float = Field(40.0, gt=0, le=100)
    nudge_n: int = Field(20, ge=1, le=100)
    nudge_pass_pct: float = Field(50.0, ge=0, le=100)
    min_oos_trades: int = Field(15, ge=0)
    min_persistence: float = Field(55.0, ge=0, le=200)
    random_n: int = Field(100, ge=1, le=500)


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = "H1"
    generations: int = Field(20, ge=1, le=200)
    population: int = Field(3000, ge=4, le=5000)
    breed_pop: int = Field(300, ge=4, le=1000)
    seed: int = 0
    tribes: list[str] = Field(default_factory=lambda: list(TRIBES))
    gates: GatesIn = Field(default_factory=GatesIn)

    @field_validator("tribes")
    @classmethod
    def _tribes_ok(cls, v: list[str]) -> list[str]:
        if not v or any(t not in TRIBES for t in v):
            raise ValueError(f"tribes must be a subset of {TRIBES}")
        return v

    @field_validator("timeframe")
    @classmethod
    def _tf_ok(cls, v: str) -> str:
        from .bars import timeframe_minutes

        timeframe_minutes(v)
        return v.upper()


class CampaignCreated(BaseModel):
    campaign_id: str
    status: str = "queued"


class ParityRequest(BaseModel):
    mt5_net_return: float


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1)
    strategy_ids: list[str] = Field(min_length=1)
    target_heat_pct: float = Field(gt=0, le=100)
    symbol_lock: bool = True
    sizing_mode: str = "equal_heat"

    @field_validator("sizing_mode")
    @classmethod
    def _mode_ok(cls, v: str) -> str:
        return canonical_mode(v)


class PortfolioDeploy(BaseModel):
    target_risk_pct_per_bot: float | None = Field(None, gt=0, le=100)
    incubation: bool = True


class PilotTokenRequest(BaseModel):
    pilot_id: str = Field(min_length=1)


class RungRequest(BaseModel):
    rung: Literal["INCUBATION", "PROVING", "FULL"]
    reason: str = ""


class AutoRequest(BaseModel):
    auto: bool


class PauseRequest(BaseModel):
    paused: bool


class PauseAllRequest(BaseModel):
    paused: bool
    reason: str | None = None


# ----------------------------------------------------------------------------- pilot envelope (SPEC §5)
class PilotAccount(BaseModel):
    login: int
    server: str = ""
    balance: float = 0.0
    equity: float = 0.0
    currency: str = "USD"


class PilotChart(BaseModel):
    symbol: str | None = None
    period_minutes: int | None = None
    chart_id: int | None = None


class PilotTerminal(BaseModel):
    connected: bool | None = None
    trade_allowed: bool | None = None
    trade_allowed_expert: bool | None = None


class PilotBot(BaseModel):
    magic: str
    symbol: str = ""
    positions: int = 0
    last_deal_at: str | None = None


class PilotTrade(BaseModel):
    ticket: int
    position_id: int | None = None
    magic: str = ""
    symbol: str = ""
    direction: Literal["buy", "sell"] = "buy"
    lots: float = 0.0
    open_time: str = ""
    close_time: str = ""
    open_price: float = 0.0
    close_price: float = 0.0
    profit: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    reason: str = ""
    equity_after: float | None = None


class PilotEnvelope(BaseModel):
    v: Literal[1] = 1
    type: Literal["heartbeat", "attach", "trade", "status"]
    sent_at: str
    pilot_id: str
    account: PilotAccount
    chart: PilotChart | None = None
    terminal: PilotTerminal | None = None
    bots: list[PilotBot] | None = None
    trade: PilotTrade | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _trade_required(self) -> "PilotEnvelope":
        if self.type == "trade" and self.trade is None:
            raise ValueError("trade messages must carry a trade object")
        return self
