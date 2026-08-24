from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FavoriteIndicator(Base):
    __tablename__ = "favorite_indicators"
    __table_args__ = (UniqueConstraint("user_id", "indicator_id", name="uq_favorite_user_indicator"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicator_definitions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
