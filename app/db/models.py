import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


class BotRun(Base):
    __tablename__ = "bot_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    bot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    bot_name: Mapped[str] = mapped_column(String(200), nullable=False)
    browser_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.PENDING, nullable=False, index=True
    )
    challenge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bot_id": self.bot_id,
            "bot_name": self.bot_name,
            "browser_mode": self.browser_mode,
            "status": self.status.value if isinstance(self.status, RunStatus) else self.status,
            "challenge_id": self.challenge_id,
            "error_details": self.error_details,
            "result_message": self.result_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }