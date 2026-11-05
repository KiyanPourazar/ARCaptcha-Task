from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import TimeoutException

from app.bots.arcaptcha_selenium import (
    ArCaptchaSeleniumBot,
    CaptchaBlockedError,
    MissingChallengeIdError,
    VerificationFailedError,
)
from app.bots.base import BotContext, RunOutcome


def _context(**overrides) -> BotContext:
    base = dict(
        headless=True,
        username="demo",
        password="demo",
        target_url="https://demo.arcaptcha.co",
        selenium_remote_url=None,
        page_load_timeout=5,
        captcha_wait_timeout=2,
        login_wait_timeout=2,
        stealth=False,
        humanize_delays=False,
    )
    base.update(overrides)
    return BotContext(**base)


@pytest.fixture()
def bot() -> ArCaptchaSeleniumBot:
    return ArCaptchaSeleniumBot()


def test_success_flow(bot: ArCaptchaSeleniumBot):
    driver = MagicMock()
    with (
        patch("app.bots.arcaptcha_selenium.create_driver", return_value=driver),
        patch.object(bot, "_execute_flow", return_value="challenge-abc-123"),
    ):
        result = bot.run(_context())

    assert result.outcome == RunOutcome.SUCCESS
    assert result.challenge_id == "challenge-abc-123"
    driver.quit.assert_called_once()


def test_missing_challenge_id(bot: ArCaptchaSeleniumBot):
    driver = MagicMock()
    with (
        patch("app.bots.arcaptcha_selenium.create_driver", return_value=driver),
        patch.object(
            bot,
            "_execute_flow",
            side_effect=MissingChallengeIdError("no token"),
        ),
    ):
        result = bot.run(_context())

    assert result.outcome == RunOutcome.FAILED
    assert "challenge_id" in (result.message or "").lower()


def test_captcha_blocked(bot: ArCaptchaSeleniumBot):
    driver = MagicMock()
    with (
        patch("app.bots.arcaptcha_selenium.create_driver", return_value=driver),
        patch.object(
            bot,
            "_execute_flow",
            side_effect=CaptchaBlockedError("visual challenge"),
        ),
    ):
        result = bot.run(_context())

    assert result.outcome == RunOutcome.BLOCKED


def test_timeout(bot: ArCaptchaSeleniumBot):
    driver = MagicMock()
    with (
        patch("app.bots.arcaptcha_selenium.create_driver", return_value=driver),
        patch.object(bot, "_execute_flow", side_effect=TimeoutException("wait")),
    ):
        result = bot.run(_context())

    assert result.outcome == RunOutcome.TIMEOUT


def test_verification_failed_keeps_challenge_id(bot: ArCaptchaSeleniumBot):
    """challenge_id obtained before failed verification must still be reported."""
    driver = MagicMock()
    with (
        patch("app.bots.arcaptcha_selenium.create_driver", return_value=driver),
        patch.object(
            bot,
            "_execute_flow",
            side_effect=VerificationFailedError("nope", challenge_id="kept-token-999"),
        ),
    ):
        result = bot.run(_context())

    assert result.outcome == RunOutcome.FAILED
    assert result.challenge_id == "kept-token-999"
    assert "verification" in (result.message or "").lower()


def test_submit_alone_is_not_success(bot: ArCaptchaSeleniumBot):
    driver = MagicMock()
    driver.execute_script.return_value = {"success": False, "error": None}
    button = MagicMock()
    button.is_displayed.return_value = True
    button.is_enabled.return_value = True
    button.text = "Login"
    driver.find_elements.return_value = [button]

    with patch.object(bot, "_find_login_button", return_value=button):
        with pytest.raises(VerificationFailedError):
            bot._submit_and_verify(driver, _context(login_wait_timeout=1), "token-12345678")
