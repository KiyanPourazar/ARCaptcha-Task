from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class BotContext:
    """Runtime inputs shared with every bot implementation."""

    headless: bool
    username: str
    password: str
    target_url: str
    selenium_remote_url: str | None = None
    chrome_binary: str | None = None
    page_load_timeout: int = 45
    captcha_wait_timeout: int = 30
    login_wait_timeout: int = 20
    stealth: bool = True
    humanize_delays: bool = True
    # "uc" = SeleniumBase UC Mode (preferred against ArCaptcha blocking)
    # "remote" = classic Remote/local WebDriver
    driver_mode: str = "uc"
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class BotResult:
    outcome: RunOutcome
    challenge_id: str | None = None
    message: str | None = None
    error_details: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.outcome == RunOutcome.SUCCESS


class BrowserBot(ABC):
    """Contract every bot must implement to plug into the platform."""

    id: str
    name: str
    description: str
    engine: str = "generic"

    @abstractmethod
    def run(self, context: BotContext) -> BotResult:
        """Execute the bot once and return a structured result."""

    def info(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "engine": self.engine,
        }
