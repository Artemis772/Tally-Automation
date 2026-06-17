"""Configuration loaded from environment variables (optionally via a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env if present. Real environment variables take precedence.
load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class TallyConfig:
    """Runtime configuration for the Tally MCP server."""

    host: str = "localhost"
    port: int = 9000
    company: str = ""          # default company; "" means Tally's active company
    timeout: int = 30          # seconds
    allow_writes: bool = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> "TallyConfig":
        return cls(
            host=os.getenv("TALLY_HOST", "localhost").strip() or "localhost",
            port=_get_int("TALLY_PORT", 9000),
            company=os.getenv("TALLY_COMPANY", "").strip(),
            timeout=_get_int("TALLY_TIMEOUT", 30),
            allow_writes=_get_bool("TALLY_ALLOW_WRITES", False),
        )


# Singleton-ish convenience instance.
config = TallyConfig.from_env()
