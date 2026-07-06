"""Application configuration loaded from environment (.env).

Nothing is hardcoded — OpenSky credentials and the Redis URL come from the
environment. See .env.example for the expected keys.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- OpenSky ---
    # Preferred: OAuth2 client credentials (OpenSky's current auth scheme).
    opensky_client_id: str | None = None
    opensky_client_secret: str | None = None
    # Legacy basic-auth fallback (deprecated by OpenSky but still works for some accounts).
    opensky_username: str | None = None
    opensky_password: str | None = None

    opensky_base_url: str = "https://opensky-network.org/api"
    opensky_token_url: str = (
        "https://auth.opensky-network.org/auth/realms/opensky-network/"
        "protocol/openid-connect/token"
    )

    # How often the ingestion loop polls OpenSky, in seconds. Authenticated users
    # get a higher rate limit; anonymous callers should stay well above ~10s.
    poll_interval: float = 8.0

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    # Per-flight state TTL (seconds). Planes that stop transmitting age out after this.
    flight_ttl: int = 60

    # --- Server ---
    # How often the WS server recomputes and pushes region deltas to clients.
    push_interval: float = 2.0

    @property
    def has_oauth(self) -> bool:
        return bool(self.opensky_client_id and self.opensky_client_secret)

    @property
    def has_basic_auth(self) -> bool:
        return bool(self.opensky_username and self.opensky_password)


settings = Settings()
