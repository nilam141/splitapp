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
    # Invite links (S6-B-4): the url returned by GET /groups/{id}/invite-link is this base plus the token.
    invite_base_url: str = "https://splitapp.example/join/"
    reset_url_base: str = "https://splitapp.example/reset-password?token="
    # Object storage (S6-B-5, S6-B-7). `local` keeps files on disk and serves them through signed `/files/...` URLs.
    storage_dir: str = "var/storage"
    storage_public_base_url: str = "http://localhost:8000/files"
    storage_signing_secret: str = ""  # empty = use jwt_secret
    receipt_url_seconds: int = 900
    export_url_seconds: int = 900
    export_retention_hours: int = 24
    # Outbound email (S6-B-3). Empty smtp_host = console/log sender.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    email_from: str = "SplitApp <no-reply@splitapp.example>"
    # Push via FCM HTTP v1 (S6-B-3). Empty project id = console/log sender. The access token comes from
    # `fcm_access_token` or, if google-auth is installed, from the service-account file `fcm_credentials_file`.
    fcm_project_id: str = ""
    fcm_access_token: str = ""
    fcm_credentials_file: str = ""
    # Background jobs (S6-B-2): `python -m app.scheduler` runs them in a loop at this interval.
    scheduler_interval_seconds: int = 900


    @model_validator(mode="after")
    def _refuse_dev_secret_in_production(self) -> "Settings":
        if self.env.lower() in PRODUCTION_ENVS and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set to a non-default value when ENV=production")
        return self


settings = Settings()
