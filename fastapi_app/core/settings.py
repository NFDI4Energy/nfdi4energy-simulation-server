"""Environment configuration without import-time resource creation."""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    resources_dir: str = "/data/resources"
    results_dir: str = "/data/results"
    redis_host: str = "redis"
    database_url: str = "sqlite:///./simserver_dev.db"
    session_secret: str = field(default="", repr=False)
    auth_disabled: bool = False
    rabbitmq_host: str = "rabbitmq"
    oidc_client_id: str = ""
    oidc_client_secret: str = field(default="", repr=False)
    oidc_discovery_url: str = "https://regapp.nfdi-aai.de/oidc/realms/nfdi/.well-known/openid-configuration"
    oidc_redirect_uri: str = "https://localhost:5001/auth/callback"
    scenario_limit: int = 10 * 1024 * 1024
    resource_limit: int = 512 * 1024 * 1024
    total_limit: int = 2 * 1024 * 1024 * 1024
    resource_count: int = 100

    @classmethod
    def from_env(cls):
        return cls(
            resources_dir=os.getenv("RESOURCES_DIR", cls.resources_dir),
            results_dir=os.getenv("RESULTS_DIR", cls.results_dir),
            redis_host=os.getenv("REDIS_HOST", cls.redis_host),
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            session_secret=os.getenv("SESSION_SECRET", ""),
            auth_disabled=os.getenv("AUTH_DISABLED", "false").strip().lower() == "true",
            rabbitmq_host=os.getenv("RABBITMQ_HOST", cls.rabbitmq_host),
            oidc_client_id=os.getenv("OIDC_CLIENT_ID", ""),
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET", ""),
            oidc_discovery_url=os.getenv("OIDC_DISCOVERY_URL", cls.oidc_discovery_url),
            oidc_redirect_uri=os.getenv("OIDC_REDIRECT_URI", cls.oidc_redirect_uri),
            scenario_limit=int(os.getenv("SCENARIO_UPLOAD_LIMIT", cls.scenario_limit)),
            resource_limit=int(os.getenv("RESOURCE_UPLOAD_LIMIT", cls.resource_limit)),
            total_limit=int(os.getenv("TOTAL_UPLOAD_LIMIT", cls.total_limit)),
            resource_count=int(os.getenv("RESOURCE_UPLOAD_COUNT", cls.resource_count)),
        )

    def validate(self):
        if not self.session_secret:
            raise RuntimeError("SESSION_SECRET must be configured")
        if not self.auth_disabled and (not self.oidc_client_id or not self.oidc_client_secret):
            raise RuntimeError("OIDC_CLIENT_ID and OIDC_CLIENT_SECRET must be configured")
        if min(self.scenario_limit, self.resource_limit, self.total_limit, self.resource_count) <= 0:
            raise RuntimeError("Upload limits must be positive")
