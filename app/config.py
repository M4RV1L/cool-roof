from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Sentinel Hub
    sentinel_client_id: str
    sentinel_client_secret: str
    sentinel_instance_id: str

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # Physical / economic constants
    default_baseline_albedo: float = 0.15
    cool_roof_albedo: float = 0.75
    electricity_price_eur_kwh: float = 0.25
    cooling_base_temp: float = 18.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
