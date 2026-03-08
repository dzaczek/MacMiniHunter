from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("product_links.id"), nullable=False)
    price_chf: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    availability: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    product_link: Mapped["ProductLink"] = relationship(back_populates="price_history")

    def __repr__(self) -> str:
        return (
            f"<PriceHistory(id={self.id}, link_id={self.link_id}, "
            f"price_chf={self.price_chf}, scraped_at='{self.scraped_at}')>"
        )
