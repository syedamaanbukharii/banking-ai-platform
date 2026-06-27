"""Application configuration.

All configuration is environment-driven (12-factor). No secrets live in the
repository. In non-local environments the app refuses to start with placeholder
secrets, which prevents accidentally shipping dev credentials.
"""

from __future__ import annotations

import functools
from enum import StrEnum

from pydantic import computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel placeholder (NOT a real secret); its presence outside local dev
# makes the app refuse to boot. See _enforce_production_secrets below.
_PLACEHOLDER_SECRET = "dev-only-change-me-please-32+chars-long-string"  # nosec B105


class AppEnv(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    LOCAL = "local"
    OIDC = "oidc"


class RouterPolicy(StrEnum):
    PREFER_ONLINE = "prefer_online"
    OFFLINE_ONLY = "offline_only"
    ONLINE_ONLY = "online_only"


class VectorBackend(StrEnum):
    MEMORY = "memory"
    PGVECTOR = "pgvector"


class WorkflowBackend(StrEnum):
    INPROCESS = "inprocess"
    TEMPORAL = "temporal"


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Field names are lower-snake-case mirrors of the upper-snake-case env vars
    documented in ``.env.example`` (matching is case-insensitive).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: AppEnv = AppEnv.LOCAL
    app_name: str = "Banking AI Platform"
    app_debug: bool = True
    app_host: str = "0.0.0.0"  # nosec B104 - bind addr is operator-controlled via env
    app_port: int = 8000
    app_log_level: str = "INFO"
    app_log_json: bool = True
    app_cors_origins: str = "http://localhost:3000"

    # --- Security ---
    security_jwt_secret: str = _PLACEHOLDER_SECRET
    security_jwt_algorithm: str = "HS256"
    security_access_token_ttl_seconds: int = 900
    security_refresh_token_ttl_seconds: int = 1_209_600
    security_cookie_secure: bool = False
    security_cookie_domain: str = "localhost"
    security_rate_limit_per_minute: int = 120
    security_auth_mode: AuthMode = AuthMode.LOCAL

    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_jwks_url: str = ""

    # --- Database ---
    database_url: str = "postgresql+asyncpg://banking:banking@localhost:5432/banking"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_echo: bool = False

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Storage ---
    storage_endpoint_url: str = "http://localhost:9000"
    storage_region: str = "us-east-1"
    storage_bucket: str = "banking-documents"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_use_local_fs: bool = True

    # --- Vector store ---
    vector_backend: VectorBackend = VectorBackend.MEMORY
    vector_dimensions: int = 384

    # --- LLM router ---
    llm_router_policy: RouterPolicy = RouterPolicy.PREFER_ONLINE
    llm_primary_provider: str = "groq"
    llm_fallback_provider: str = "local_gemma"
    llm_request_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"

    local_gemma_base_url: str = "http://localhost:11434/v1"
    local_gemma_model: str = "gemma2:9b"

    # --- Workflow ---
    workflow_backend: WorkflowBackend = WorkflowBackend.INPROCESS
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "banking-ai"

    # --- Observability ---
    otel_enabled: bool = False
    metrics_enabled: bool = True

    # --- Dev seed ---
    seed_admin_email: str = "admin@local.dev"
    seed_admin_password: str = "Admin123!Local"

    @field_validator("app_log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"app_log_level must be one of {sorted(allowed)}")
        return upper

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> Settings:
        """Refuse to boot with placeholder/empty secrets outside local dev."""
        if self.app_env is AppEnv.LOCAL:
            return self
        if self.security_jwt_secret in ("", _PLACEHOLDER_SECRET):
            raise ValueError(
                "SECURITY_JWT_SECRET must be set to a real secret in non-local environments."
            )
        if len(self.security_jwt_secret) < 32:
            raise ValueError("SECURITY_JWT_SECRET must be at least 32 characters.")
        if self.security_auth_mode is AuthMode.OIDC and not self.oidc_client_secret:
            raise ValueError("OIDC_CLIENT_SECRET is required when SECURITY_AUTH_MODE=oidc.")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]


@functools.lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one read of the environment per process)."""
    return Settings()
