from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str

    # Provider selection: openai_compatible (default) or anthropic.
    LLM_PROVIDER: str = "openai_compatible"

    # OpenAI-compatible credentials (recommended for relay providers).
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # Backward-compatible AI relay fields used by existing deployments.
    AI_API_KEY: str = ""
    AI_BASE_URL: str = "https://api.anthropic.com"

    # Optional direct Anthropic key.
    ANTHROPIC_API_KEY: str = ""

    AGENT_MODEL: str = "claude-3-5-sonnet-20241022"
    DEBUG: str = "false"
    JWT_SECRET_KEY: str
    CORS_ORIGINS: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def debug_enabled(self) -> bool:
        value = str(self.DEBUG).strip().lower()
        return value in {"1", "true", "yes", "on", "debug", "dev", "development"}


settings = Settings()