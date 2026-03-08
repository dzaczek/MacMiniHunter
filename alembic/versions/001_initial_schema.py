"""Initial schema - stores, products, product_links, price_history

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stores
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Product condition enum
    product_condition = sa.Enum("new", "used", "refurbished", name="product_condition")
    product_condition.create(op.get_bind(), checkfirst=True)

    # Products
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("chip", sa.String(50), nullable=False),
        sa.Column("ram", sa.Integer(), nullable=False),
        sa.Column("ssd", sa.Integer(), nullable=False),
        sa.Column(
            "condition",
            product_condition,
            nullable=False,
            server_default="new",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Product links
    op.create_table(
        "product_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Price history
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("price_chf", sa.Numeric(10, 2), nullable=False),
        sa.Column("availability", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["link_id"], ["product_links.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes for common queries
    op.create_index("ix_price_history_link_id", "price_history", ["link_id"])
    op.create_index("ix_price_history_scraped_at", "price_history", ["scraped_at"])
    op.create_index("ix_product_links_product_id", "product_links", ["product_id"])
    op.create_index("ix_product_links_store_id", "product_links", ["store_id"])

    # Seed default stores
    stores_table = sa.table(
        "stores",
        sa.column("name", sa.String),
        sa.column("base_url", sa.String),
    )
    op.bulk_insert(
        stores_table,
        [
            {"name": "Digitec", "base_url": "https://www.digitec.ch"},
            {"name": "Galaxus", "base_url": "https://www.galaxus.ch"},
            {"name": "Ricardo", "base_url": "https://www.ricardo.ch"},
            {"name": "Toppreise", "base_url": "https://www.toppreise.ch"},
            {"name": "Brack", "base_url": "https://www.brack.ch"},
        ],
    )


def downgrade() -> None:
    op.drop_table("price_history")
    op.drop_table("product_links")
    op.drop_table("products")
    op.drop_table("stores")
    sa.Enum(name="product_condition").drop(op.get_bind(), checkfirst=True)
