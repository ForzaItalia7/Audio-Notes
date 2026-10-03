from datetime import datetime

from sqlalchemy import DateTime, String, Text, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stored_at: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="uploaded",
    )
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    gnani_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (UniqueConstraint("upload_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    language_code: Mapped[str] = mapped_column(String(10), default="hi-IN")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    failures: Mapped[int] = mapped_column(default=0)
