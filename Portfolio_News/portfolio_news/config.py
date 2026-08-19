from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_TICKERS_JSON = ROOT / "tickers.example.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    poll_interval_sec: int = 900
    database_url: str = f"sqlite:///{(DATA_DIR / 'news.db').as_posix()}"
    poll_limit: int = 0
    host: str = "127.0.0.1"
    port: int = 8765
    tickers_json: Path = DEFAULT_TICKERS_JSON

    # BCS Trade API (read-only). Never commit real token.
    bcs_trade_refresh_token: str = ""
    bcs_trade_client_id: str = "trade-api-read"


def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
