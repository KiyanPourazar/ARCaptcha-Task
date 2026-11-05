from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.bots.base import BotContext, RunOutcome
from app.bots.registry import BotRegistry
from app.config import Settings
from app.db.models import BotRun, RunStatus

logger = logging.getLogger(__name__)

OUTCOME_TO_STATUS = {
    RunOutcome.SUCCESS: RunStatus.SUCCESS,
    RunOutcome.FAILED: RunStatus.FAILED,
    RunOutcome.BLOCKED: RunStatus.BLOCKED,
    RunOutcome.TIMEOUT: RunStatus.TIMEOUT,
}


class BotRunner:
    def __init__(self, registry: BotRegistry, settings: Settings) -> None:
        self.registry = registry
        self.settings = settings

    def start_run(self, db: Session, bot_id: str, headless: bool) -> BotRun:
        bot = self.registry.require(bot_id)
        run = BotRun(
            bot_id=bot.id,
            bot_name=bot.name,
            browser_mode="headless" if headless else "headful",
            status=RunStatus.PENDING,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def execute(self, db: Session, run_id: str) -> BotRun:
        run = db.get(BotRun, run_id)
        if run is None:
            raise KeyError(f"Run not found: {run_id}")

        bot = self.registry.require(run.bot_id)
        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        context = BotContext(
            headless=run.browser_mode == "headless",
            username=self.settings.bot_username,
            password=self.settings.bot_password,
            target_url=self.settings.target_url,
            selenium_remote_url=self.settings.selenium_remote_url or None,
            chrome_binary=self.settings.chrome_binary,
            page_load_timeout=self.settings.page_load_timeout,
            captcha_wait_timeout=self.settings.captcha_wait_timeout,
            login_wait_timeout=self.settings.login_wait_timeout,
            stealth=self.settings.bot_stealth,
            humanize_delays=self.settings.humanize_delays,
            driver_mode=(self.settings.driver_mode or "uc").lower(),
        )

        try:
            result = bot.run(context)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Bot crashed for run %s", run_id)
            run.status = RunStatus.FAILED
            run.error_details = f"Unhandled exception: {exc}"
            run.ended_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(run)
            return run

        # Persist challenge_id whenever obtained, including failed/blocked runs.
        if result.challenge_id:
            run.challenge_id = result.challenge_id

        run.status = OUTCOME_TO_STATUS.get(result.outcome, RunStatus.FAILED)
        run.result_message = result.message
        run.error_details = result.error_details
        run.ended_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run