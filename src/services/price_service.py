"""Service for storing scraped prices and detecting price drops."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from src.models import Store, Product, ProductLink, PriceHistory
from src.models.product import Condition
from src.utils.validators import ScrapedPrice, parse_specs_from_title

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self, session: Session):
        self.session = session

    def store_scraped_prices(self, store_name: str, prices: list[ScrapedPrice]) -> int:
        """Store scraped prices in the database. Returns count of saved records.

        If a ScrapedPrice has store_name set (e.g. from comparison sites like Toppreise),
        it will be stored under that shop name instead of the scraper's store_name.
        """
        # Cache stores to avoid repeated lookups
        store_cache: dict[str, Store] = {}

        def get_store(name: str) -> Store:
            if name in store_cache:
                return store_cache[name]
            store = self.session.execute(
                select(Store).where(Store.name == name)
            ).scalar_one_or_none()
            if not store:
                store = Store(name=name, base_url="")
                self.session.add(store)
                self.session.flush()
                logger.info(f"Created store '{name}' in database")
            store_cache[name] = store
            return store

        saved = 0
        for scraped in prices:
            try:
                # Use per-item store_name if set (from comparison sites),
                # otherwise use the scraper's store_name
                effective_store_name = scraped.store_name or store_name
                store = get_store(effective_store_name)

                product_link = self._get_or_create_product_link(store, scraped)
                if product_link is None:
                    continue

                # Insert price history record
                price_record = PriceHistory(
                    link_id=product_link.id,
                    price_chf=scraped.price_chf,
                    availability=scraped.availability,
                )
                self.session.add(price_record)
                saved += 1

            except Exception as e:
                logger.error(f"Error saving price for '{scraped.title}': {e}")

        self.session.commit()
        logger.info(f"[{store_name}] Saved {saved}/{len(prices)} price records")
        return saved

    def _get_or_create_product_link(
        self, store: Store, scraped: ScrapedPrice
    ) -> Optional[ProductLink]:
        """Find existing product link or create product + link."""
        # Try to find by external_id first
        if scraped.external_id:
            existing = self.session.execute(
                select(ProductLink).where(
                    and_(
                        ProductLink.store_id == store.id,
                        ProductLink.external_id == scraped.external_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return existing

        # Try to find by URL
        existing = self.session.execute(
            select(ProductLink).where(
                and_(
                    ProductLink.store_id == store.id,
                    ProductLink.url == scraped.url,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        # Parse product specs - try SKU first, then title parsing
        specs = parse_specs_from_title(scraped.title, external_id=scraped.external_id)
        if specs is None:
            logger.debug(f"Skipping (unrecognized config): '{scraped.title}' (id={scraped.external_id})")
            return None
        else:
            # Find or create the normalized product
            # Match by chip + ram + ssd + cpu/gpu cores (if known)
            filters = [
                Product.chip == specs.chip,
                Product.ram == specs.ram,
                Product.ssd == specs.ssd,
            ]
            if specs.cpu_cores is not None:
                filters.append(Product.cpu_cores == specs.cpu_cores)
            if specs.gpu_cores is not None:
                filters.append(Product.gpu_cores == specs.gpu_cores)

            product = self.session.execute(
                select(Product).where(and_(*filters))
            ).scalar_one_or_none()

            if not product:
                # Build descriptive name
                cores_str = ""
                if specs.cpu_cores and specs.gpu_cores:
                    cores_str = f" ({specs.cpu_cores}c CPU/{specs.gpu_cores}c GPU)"
                product = Product(
                    name=f"Mac Mini {specs.chip} {specs.ram}GB {specs.ssd}GB{cores_str}",
                    chip=specs.chip,
                    ram=specs.ram,
                    ssd=specs.ssd,
                    cpu_cores=specs.cpu_cores,
                    gpu_cores=specs.gpu_cores,
                    condition=Condition.NEW,
                )
                self.session.add(product)
                self.session.flush()

        link = ProductLink(
            product_id=product.id,
            store_id=store.id,
            url=scraped.url,
            external_id=scraped.external_id,
        )
        self.session.add(link)
        self.session.flush()
        return link

    def detect_price_drops(
        self, days: int = 7, threshold_pct: float = 5.0
    ) -> list[dict]:
        """Find products where current price is lower than 7-day average.

        Also checks absolute thresholds for known configurations.

        Returns list of dicts with drop details.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Subquery: average price per link_id over last N days
        avg_subq = (
            select(
                PriceHistory.link_id,
                func.avg(PriceHistory.price_chf).label("avg_price"),
            )
            .where(PriceHistory.scraped_at >= cutoff)
            .group_by(PriceHistory.link_id)
            .subquery()
        )

        # Subquery: latest price per link_id
        latest_subq = (
            select(
                PriceHistory.link_id,
                PriceHistory.price_chf.label("current_price"),
                PriceHistory.scraped_at,
            )
            .distinct(PriceHistory.link_id)
            .order_by(PriceHistory.link_id, PriceHistory.scraped_at.desc())
            .subquery()
        )

        # Join everything
        query = (
            select(
                ProductLink,
                Product,
                Store,
                latest_subq.c.current_price,
                avg_subq.c.avg_price,
            )
            .join(Product, ProductLink.product_id == Product.id)
            .join(Store, ProductLink.store_id == Store.id)
            .join(latest_subq, ProductLink.id == latest_subq.c.link_id)
            .join(avg_subq, ProductLink.id == avg_subq.c.link_id)
            .where(latest_subq.c.current_price < avg_subq.c.avg_price)
        )

        results = self.session.execute(query).all()

        drops = []
        for link, product, store, current, avg in results:
            drop_pct = ((float(avg) - float(current)) / float(avg)) * 100

            if drop_pct < threshold_pct:
                continue

            drops.append({
                "product_name": product.name,
                "chip": product.chip,
                "ram": product.ram,
                "ssd": product.ssd,
                "store": store.name,
                "current_price": float(current),
                "avg_price": round(float(avg), 2),
                "drop_pct": round(drop_pct, 1),
                "url": link.url,
            })

        # Also check absolute thresholds
        absolute_deals = self._check_absolute_thresholds()
        drops.extend(absolute_deals)

        return drops

    def _check_absolute_thresholds(self) -> list[dict]:
        """Check if any current prices are significantly below the all-time average.

        Instead of hardcoded thresholds, we dynamically compute them:
        - A deal is when current price is > 15% below the all-time average for that config.
        """
        deals = []

        # Find all tracked configurations
        configs = self.session.execute(
            select(Product.chip, Product.ram, Product.ssd)
            .distinct()
        ).all()

        for chip, ram, ssd in configs:
            # Get all-time average price for this config
            avg_result = self.session.execute(
                select(func.avg(PriceHistory.price_chf).label("avg_price"))
                .join(ProductLink, PriceHistory.link_id == ProductLink.id)
                .join(Product, ProductLink.product_id == Product.id)
                .where(
                    and_(
                        Product.chip == chip,
                        Product.ram == ram,
                        Product.ssd == ssd,
                    )
                )
            ).scalar()

            if not avg_result:
                continue

            avg_price = float(avg_result)

            # Find latest price for this config (cheapest across all stores)
            result = self.session.execute(
                select(
                    PriceHistory.price_chf,
                    ProductLink.url,
                    Store.name.label("store_name"),
                )
                .join(ProductLink, PriceHistory.link_id == ProductLink.id)
                .join(Product, ProductLink.product_id == Product.id)
                .join(Store, ProductLink.store_id == Store.id)
                .where(
                    and_(
                        Product.chip == chip,
                        Product.ram == ram,
                        Product.ssd == ssd,
                    )
                )
                .order_by(PriceHistory.scraped_at.desc())
                .limit(1)
            ).first()

            if not result:
                continue

            current = float(result.price_chf)
            threshold = avg_price * 0.85  # 15% below average = deal

            if current <= threshold:
                drop_pct = round(((avg_price - current) / avg_price) * 100, 1)
                deals.append({
                    "product_name": f"Mac Mini {chip} {ram}GB {ssd}GB",
                    "chip": chip,
                    "ram": ram,
                    "ssd": ssd,
                    "store": result.store_name,
                    "current_price": current,
                    "avg_price": round(avg_price, 2),
                    "drop_pct": drop_pct,
                    "url": result.url,
                    "absolute_deal": True,
                })

        return deals
