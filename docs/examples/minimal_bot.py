"""
Minimal example: implement and register a new bot.

1. Subclass BrowserBot
2. Implement run(context) -> BotResult
3. Call register_bot(...) at import time
4. Import the module from app/bots/__init__.py (or another startup import)

This example intentionally does not open a browser; it shows the contract only.
"""

from __future__ import annotations

from app.bots.base import BotContext, BotResult, BrowserBot, RunOutcome
from app.bots.registry import register_bot


class PingBot(BrowserBot):
    id = "example_ping"
    name = "Example Ping Bot"
    description = "Minimal registered bot that returns success without a browser."
    engine = "none"

    def run(self, context: BotContext) -> BotResult:
        return BotResult(
            outcome=RunOutcome.SUCCESS,
            message=f"Ping OK (headless={context.headless})",
            metadata={"target_url": context.target_url},
        )


# Uncomment to activate:
# register_bot(PingBot())
