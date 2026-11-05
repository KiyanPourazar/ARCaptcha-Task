from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Extensible Browser Bot Platform",
    version=__version__,
    description="Define, run, and monitor browser bots with pluggable engines.",
)


@app.on_event("startup")
def on_startup() -> None:
    # Import bots package so concrete bots register themselves.
    import app.bots  # noqa: F401

    init_db()


app.include_router(router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
