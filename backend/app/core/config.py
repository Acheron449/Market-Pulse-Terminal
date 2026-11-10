"""Application settings, read from the environment and the repository `.env`.

Every knob in SRS Appendix A lives here rather than in a provider or a component
(`AGENTS.md` §6). Lists and maps are plain comma-separated strings in the environment so a
`.env` file stays readable; validators parse them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"
DATA_DIR = REPO_ROOT / "backend" / "data"


def _csv_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("expected a comma-separated list")


def _pairs(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {str(key): float(item) for key, item in value.items()}
    if not isinstance(value, str):
        raise ValueError("expected key=value pairs")
    parsed: dict[str, float] = {}
    for part in value.split(","):
        if not part.strip():
            continue
        key, _, item = part.partition("=")
        parsed[key.strip()] = float(item)
    return parsed


CsvList = Annotated[list[str], NoDecode, BeforeValidator(_csv_list)]
PairMap = Annotated[dict[str, float], NoDecode, BeforeValidator(_pairs)]


class Settings(BaseSettings):
    """Runtime configuration. Defaults keep a fresh clone working with no keys at all."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Market Pulse Terminal"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # HTTP clients (SRS §7.3)
    http_connect_timeout_seconds: float = 5.0
    http_timeout_seconds: float = 8.0

    # Opt-in for live providers. Off by default so a fresh clone (and every test) serves
    # the recorded snapshot instead of reaching out to Yahoo/Alpaca/Finnhub.
    enable_live_data: bool = False

    # Provider credentials: only ever read here and never sent to the browser.
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_feed: Literal["iex", "sip"] = "iex"
    finnhub_api_key: str | None = None

    # FAILOVER order per capability (SRS §4.1, Appendix A)
    provider_order_indexes: CsvList = Field(default_factory=lambda: ["yfinance", "alpaca"])
    provider_order_movers: CsvList = Field(default_factory=lambda: ["alpaca", "yfinance"])
    provider_order_news: CsvList = Field(default_factory=lambda: ["finnhub", "alpaca"])
    provider_order_status: CsvList = Field(
        default_factory=lambda: ["alpaca", "finnhub", "calendar"]
    )

    # Rate limits and circuit breaker: 70% of each documented quota (provider-notes §3)
    alpaca_rate_per_minute: int = 140
    finnhub_rate_per_minute: int = 42
    yfinance_min_interval_seconds: int = 15
    circuit_failure_threshold: int = 3
    circuit_cooldown_seconds: int = 60

    # Snapshot
    index_symbols: CsvList = Field(
        default_factory=lambda: ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"]
    )
    sparkline_points: int = 140

    # Sentiment (SRS §10, docs/sentiment.md §8)
    sentiment_weights: PairMap = Field(
        default_factory=lambda: {
            "volatility": 0.30,
            "trend": 0.25,
            "momentum": 0.20,
            "riskAppetite": 0.15,
            "headlineTone": 0.10,
        }
    )
    sentiment_bands: PairMap = Field(
        default_factory=lambda: {"bearish": 25.0, "uncertain": 44.0, "neutral": 60.0}
    )
    sentiment_min_components: int = 3
    enable_headline_tone: bool = True
    enable_llm_summary: bool = False

    # Refresh policy (SRS §9)
    refresh_cooldown_seconds: int = 10
    quotes_refresh_seconds: int = 20
    quotes_refresh_seconds_offhours: int = 60
    quotes_refresh_seconds_closed: int = 900
    movers_refresh_seconds: int = 60
    movers_refresh_seconds_offhours: int = 180
    movers_refresh_seconds_closed: int = 1800
    news_refresh_seconds: int = 300
    news_refresh_seconds_offhours: int = 600
    news_refresh_seconds_closed: int = 1800
    status_refresh_seconds: int = 60
    history_refresh_seconds: int = 3600
    scheduler_jitter_fraction: float = 0.10
    scheduler_max_backoff_seconds: int = 300

    # Movers filters (FR-7)
    movers_min_price: float = 1.0
    movers_min_volume: float = 100_000
    movers_exclude_warrants: bool = True
    movers_exclude_leveraged_etfs: bool = True

    # Static export (FR-17)
    enable_static_export: bool = False
    static_export_path: Path = REPO_ROOT / "frontend" / "public" / "market-data.json"

    # Charts (SRS §4.4, docs/tradingview.md)
    chart_engine: Literal["lightweight", "advanced"] = "lightweight"
    chart_resolutions: CsvList = Field(default_factory=lambda: ["1", "5", "15", "60", "1D"])
    chart_live_subscription_cap: int = 10
    chart_history_cache_seconds: int = 300

    # Persistence (Phase 3: cold-start serve, FR-18)
    database_path: Path = DATA_DIR / "mpt.sqlite3"

    # Browser
    cors_origins: CsvList = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
        ]
    )
    enable_tradingview_widget: bool = False

    @property
    def alpaca_configured(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_api_secret)

    @property
    def finnhub_configured(self) -> bool:
        return bool(self.finnhub_api_key)

    @property
    def alpaca_feed_delay_seconds(self) -> int:
        """Feed delay for disclosure (provider-notes §6): IEX real-time, SIP delayed."""
        return 0 if self.alpaca_feed == "iex" else 900


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are process-wide and do not change at runtime, so parse them once."""
    return Settings()
