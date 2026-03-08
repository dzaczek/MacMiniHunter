from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Relationships
    product_links: Mapped[list["ProductLink"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Store(id={self.id}, name='{self.name}')>"
