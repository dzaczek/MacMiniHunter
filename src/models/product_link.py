from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class ProductLink(Base):
    __tablename__ = "product_links"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="product_links")
    store: Mapped["Store"] = relationship(back_populates="product_links")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="product_link", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ProductLink(id={self.id}, product_id={self.product_id}, store_id={self.store_id})>"
