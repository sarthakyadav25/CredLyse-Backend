"""
Enrollment Model

User-course enrollment with completion tracking.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.playlist import Playlist
    from app.models.video_progress import VideoProgress


class Enrollment(Base):
    """
    Enrollment model representing a user taking a course.
    
    Unique constraint ensures a user can only enroll once per course.
    
    Attributes:
        id: Integer primary key.
        user_id: Foreign key to users table.
        playlist_id: Foreign key to playlists table.
        is_completed: Whether the user has completed the course.
        certificate_url: URL to the generated certificate (if completed).
        last_active_at: Timestamp of last activity in the course.
    """
    
    __tablename__ = "enrollments"
    
    __table_args__ = (
        UniqueConstraint("user_id", "playlist_id", name="uq_user_playlist"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    playlist_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("playlists.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    certificate_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="enrollments",
    )
    playlist: Mapped["Playlist"] = relationship(
        "Playlist",
        back_populates="enrollments",
    )
    video_progress: Mapped[list["VideoProgress"]] = relationship(
        "VideoProgress",
        back_populates="enrollment",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Enrollment(id={self.id}, user_id={self.user_id}, playlist_id={self.playlist_id})>"
