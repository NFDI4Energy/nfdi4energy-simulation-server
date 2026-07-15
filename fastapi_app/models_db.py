import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    sub = Column(Text, unique=True, nullable=False, index=True)  # OIDC subject identifier
    email = Column(Text, nullable=True)
    display_name = Column(Text, nullable=True)
    issuer = Column(Text, nullable=False)
    raw_claims = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    last_login = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    tasks = relationship("Task", back_populates="owner", lazy="dynamic")

    def __repr__(self):
        return f"<User sub={self.sub!r} email={self.email!r}>"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    scenario_id = Column(Text, nullable=True)
    status = Column(String(20), default="PENDING")
    resource_files = Column(JSON, nullable=True)  # e.g. ["scenario.json", "grid.csv"]
    result_files = Column(JSON, nullable=True)     # e.g. ["result.json", "plot.png"]
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    error_message = Column(Text, nullable=True)

    owner = relationship("User", back_populates="tasks")

    def __repr__(self):
        return f"<Task id={self.id!r} user={self.user_id!r} status={self.status!r}>"
