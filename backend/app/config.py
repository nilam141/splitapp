from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEV_JWT_SECRET = "dev-only-change-me-dev-only-change-me"
PRODUCTION_ENVS = {"production", "prod"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://splitapp:splitapp@localhost:5432/splitapp"
    env: str = "development"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_seconds: int = 900
    refresh_token_days: int = 30
    # Rate limits (business_rules 11.2, OQ-38)
    login_max_failures_per_email: int = 5
    login_max_failures_per_ip: int = 20
    login_window_seconds: int = 900
    reset_max_per_email: int = 3
    reset_window_seconds: int = 3600
    # Number of trusted reverse proxies in front of the app (0 = none: use the socket peer address).
    # With N > 0 the client IP is the Nth entry from the RIGHT of X-Forwarded-For (entries appended by our own
    # proxies; anything a client prepends is ignored). Set only when every request really passes through N proxies.
    trusted_proxy_count: int = 0


    @model_validator(mode="after")
    def _refuse_dev_secret_in_production(self) -> "Settings":
        if self.env.lower() in PRODUCTION_ENVS and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set to a non-default value when ENV=production")
        return self


settings = Settings()
