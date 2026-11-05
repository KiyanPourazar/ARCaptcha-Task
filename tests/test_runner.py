from __future__ import annotations

from unittest.mock import MagicMock

from app.bots.base import BotResult, RunOutcome
from app.bots.registry import BotRegistry
from app.config import Settings
from app.db.models import RunStatus
from app.services.runner import BotRunner


def test_runner_persists_challenge_id_on_failure(db_session):
    bot = MagicMock()
    bot.id = "mock_bot"
    bot.name = "Mock Bot"
    bot.run.return_value = BotResult(
        outcome=RunOutcome.FAILED,
        challenge_id="cid-should-persist",
        message="verification failed",
        error_details="no success toast",
    )

    registry = BotRegistry()
    registry.register(bot)
    settings = Settings(
        bot_username="demo",
        bot_password="demo",
        selenium_remote_url=None,
        humanize_delays=False,
        bot_stealth=False,
    )
    runner = BotRunner(registry=registry, settings=settings)

    run = runner.start_run(db_session, bot_id="mock_bot", headless=True)
    finished = runner.execute(db_session, run.id)

    assert finished.status == RunStatus.FAILED
    assert finished.challenge_id == "cid-should-persist"
    assert finished.error_details == "no success toast"


def test_runner_records_blocked(db_session):
    bot = MagicMock()
    bot.id = "mock_bot"
    bot.name = "Mock Bot"
    bot.run.return_value = BotResult(
        outcome=RunOutcome.BLOCKED,
        challenge_id=None,
        message="blocked",
        error_details="visual challenge",
    )

    registry = BotRegistry()
    registry.register(bot)
    runner = BotRunner(
        registry=registry,
        settings=Settings(humanize_delays=False, bot_stealth=False),
    )
    run = runner.start_run(db_session, bot_id="mock_bot", headless=False)
    finished = runner.execute(db_session, run.id)

    assert finished.status == RunStatus.BLOCKED
    assert finished.browser_mode == "headful"
