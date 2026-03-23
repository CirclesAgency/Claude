"""
Central settings module. All configuration is read from environment variables
(with .env file support). Import `settings` from here throughout the app.
"""
from pathlib import Path
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite:///./outbound_machine.db"

    # HTTP client
    http_user_agent: str = (
        "Mozilla/5.0 (compatible; ProdigiResearchBot/1.0; +https://prodigi.com)"
    )
    rate_limit_delay: float = 2.0
    http_concurrency: int = 3
    http_timeout: int = 30
    http_max_retries: int = 3

    # Feature flags
    enable_screenshots: bool = False
    enable_llm: bool = False
    enable_webhook_sync: bool = False

    # LLM
    llm_provider: str = "anthropic"
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    llm_model: str = "claude-3-5-haiku-20241022"
    llm_max_tokens: int = 1024

    # CRM webhook
    crm_webhook_url: Optional[str] = None
    crm_webhook_secret: Optional[str] = None
    crm_webhook_headers: dict = {}

    # Paths
    screenshots_dir: Path = Path("./data/screenshots")
    exports_dir: Path = Path("./data/exports")
    logs_dir: Path = Path("./logs")

    # Scoring config
    scoring_config_path: Path = Path("./app/config/scoring_config.yaml")

    # AU discovery config
    au_discovery_config_path: Path = Path("./app/config/au_discovery_config.yaml")

    # Logging
    log_level: str = "INFO"

    @field_validator("screenshots_dir", "exports_dir", "logs_dir", mode="before")
    @classmethod
    def ensure_path(cls, v):
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
