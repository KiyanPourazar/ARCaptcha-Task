"""Bot package: import concrete bots so they self-register."""

from app.bots import arcaptcha_selenium  # noqa: F401
from app.bots.base import BotContext, BotResult, BrowserBot, RunOutcome
from app.bots.registry import BotRegistry, get_registry

__all__ = [
    "BotContext",
    "BotResult",
    "BrowserBot",
    "BotRegistry",
    "RunOutcome",
    "get_registry",
]