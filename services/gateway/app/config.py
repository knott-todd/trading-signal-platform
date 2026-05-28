from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gateway_port: int = 8080
    ingestion_api_url: str = "http://backend:8000"
    sse_keepalive_seconds: int = 30

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
