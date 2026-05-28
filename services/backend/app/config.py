from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    alpaca_api_key: str
    alpaca_secret_key: str
    database_url: str

    stream_resolutions: str = "1m,5m"
    stream_fallback_poll_seconds: int = 60
    max_watchlist_size: int = 50
    max_stream_tickers: int = 25
    timezone: str = "US/Eastern"

    @property
    def stream_resolutions_list(self) -> List[str]:
        return [r.strip() for r in self.stream_resolutions.split(",")]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
