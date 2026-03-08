from typing import Optional
from sqlalchemy import String, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from src.models.base import Base


class Condition(str, enum.Enum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    chip: Mapped[str] = mapped_column(String(50), nullable=False)  # M4, M4 PRO, etc.
    ram: Mapped[int] = mapped_column(nullable=False)  # in GB
    ssd: Mapped[int] = mapped_column(nullable=False)  # in GB
    cpu_cores: Mapped[Optional[int]] = mapped_column(nullable=True, default=None)  # e.g. 10, 12, 14
    gpu_cores: Mapped[Optional[int]] = mapped_column(nullable=True, default=None)  # e.g. 10, 16, 20
    condition: Mapped[Condition] = mapped_column(
        SAEnum(Condition, name="product_condition"),
        default=Condition.NEW,
        nullable=False,
    )

    # Relationships
    product_links: Mapped[list["ProductLink"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        cores = f", cpu={self.cpu_cores}c, gpu={self.gpu_cores}c" if self.cpu_cores else ""
        return (
            f"<Product(id={self.id}, name='{self.name}', "
            f"chip='{self.chip}', ram={self.ram}GB, ssd={self.ssd}GB{cores}, "
            f"condition='{self.condition.value}')>"
        )
