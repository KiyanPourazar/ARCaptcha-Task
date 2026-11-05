from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.bots.registry import BotRegistry, get_registry
from app.config import Settings, get_settings
from app.db.database import SessionLocal, get_db
from app.db.models import BotRun
from app.services.runner import BotRunner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# Bound pool so a flood of UI clicks cannot spawn unbounded Chrome processes.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bot-run")


class LaunchRequest(BaseModel):
    bot_id: str = Field(..., min_length=1)
    browser_mode: Literal["headless", "headful"] = "headless"


def get_runner(
    registry: BotRegistry = Depends(get_registry),
    settings: Settings = Depends(get_settings),
) -> BotRunner:
    return BotRunner(registry=registry, settings=settings)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/bots")
def list_bots(registry: BotRegistry = Depends(get_registry)) -> dict:
    return {"bots": [bot.info() for bot in registry.list()]}


@router.get("/runs")
def list_runs(limit: int = 50, db: Session = Depends(get_db)) -> dict:
    limit = max(1, min(limit, 200))
    runs = (
        db.query(BotRun)
        .order_by(BotRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"runs": [run.to_dict() for run in runs]}


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(BotRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.to_dict()


@router.post("/runs", status_code=202)
def launch_run(
    payload: LaunchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    runner: BotRunner = Depends(get_runner),
    registry: BotRegistry = Depends(get_registry),
) -> dict:
    if registry.get(payload.bot_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown bot: {payload.bot_id}")

    headless = payload.browser_mode == "headless"
    run = runner.start_run(db, bot_id=payload.bot_id, headless=headless)
    background_tasks.add_task(_run_in_background, run.id)
    return {"run": run.to_dict()}


def _run_in_background(run_id: str) -> None:
    def _job() -> None:
        db = SessionLocal()
        try:
            settings = get_settings()
            runner = BotRunner(registry=get_registry(), settings=settings)
            runner.execute(db, run_id)
        except Exception:
            logger.exception("Background run failed: %s", run_id)
        finally:
            db.close()

    _executor.submit(_job)
