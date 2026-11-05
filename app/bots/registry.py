from __future__ import annotations

from app.bots.base import BrowserBot


class BotRegistry:
    """Simple in-process registry for bot implementations."""

    def __init__(self) -> None:
        self._bots: dict[str, BrowserBot] = {}

    def register(self, bot: BrowserBot) -> BrowserBot:
        if not bot.id:
            raise ValueError("Bot id is required")
        if bot.id in self._bots:
            raise ValueError(f"Bot already registered: {bot.id}")
        self._bots[bot.id] = bot
        return bot

    def get(self, bot_id: str) -> BrowserBot | None:
        return self._bots.get(bot_id)

    def list(self) -> list[BrowserBot]:
        return list(self._bots.values())

    def require(self, bot_id: str) -> BrowserBot:
        bot = self.get(bot_id)
        if bot is None:
            raise KeyError(f"Unknown bot: {bot_id}")
        return bot


_registry = BotRegistry()


def get_registry() -> BotRegistry:
    return _registry


def register_bot(bot: BrowserBot) -> BrowserBot:
    return get_registry().register(bot)