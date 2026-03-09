"""Main entry point - runs scrapers on schedule and sends deal alerts via Matrix."""

import logging
import sys
import random
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.database import get_session, engine
from src.models import Base
from src.scrapers.ricardo import RicardoScraper
from src.scrapers.toppreise import ToppreiseScraper
from src.scrapers.brack import BrackScraper
from src.scrapers.galaxus import GalaxusScraper
from src.scrapers.fust import FustScraper
from src.scrapers.dqsolutions import DQSolutionsScraper
from src.scrapers.tutti import TuttiScraper
from src.scrapers.apple import AppleScraper
from src.services.price_service import PriceService
from src.services.matrix_notifier import MatrixNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# All available scrapers
SCRAPERS = [
    BrackScraper,
    FustScraper,
    AppleScraper,
    GalaxusScraper,
    DQSolutionsScraper,
    TuttiScraper,
    RicardoScraper,
    ToppreiseScraper,
]


def run_scrape_cycle():
    """Execute one full scraping cycle across all stores."""
    logger.info("=" * 60)
    logger.info(f"Starting scrape cycle at {datetime.now().isoformat()}")
    logger.info("=" * 60)

    session = get_session()
    price_service = PriceService(session)
    notifier = MatrixNotifier()
    store_counts: dict[str, int] = {}

    try:
        random.shuffle(SCRAPERS)  # Randomize order to be less predictable
        for scraper_cls in SCRAPERS:
            scraper = scraper_cls()
            prices = scraper.run()

            if prices:
                saved = price_service.store_scraped_prices(scraper.STORE_NAME, prices)
                store_counts[scraper.STORE_NAME] = saved
            else:
                store_counts[scraper.STORE_NAME] = 0
                logger.warning(f"[{scraper.STORE_NAME}] No results returned")

            # Wait between scrapers to avoid burst activity
            if scraper_cls != SCRAPERS[-1]:
                wait = random.uniform(20.0, 60.0)
                logger.info(f"Waiting {wait:.1f}s before next store...")
                time.sleep(wait)

        # Detect price drops and send alerts
        drops = price_service.detect_price_drops(days=7, threshold_pct=5.0)
        if drops:
            logger.info(f"Found {len(drops)} deal(s)!")
            for deal in drops:
                notifier.send_deal_alert(deal)
        else:
            logger.info("No price drops detected this cycle")

        # Send summary
        notifier.send_scrape_summary(store_counts)

    except Exception as e:
        logger.error(f"Scrape cycle failed: {e}", exc_info=True)
    finally:
        session.close()

    logger.info("Scrape cycle complete")


def init_db():
    """Create tables if they don't exist (fallback if Alembic hasn't run)."""
    logger.info("Ensuring database tables exist...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready")


def main():
    logger.info("Mac Mini Price Tracker starting up")
    init_db()

    # Run one cycle immediately on startup
    run_scrape_cycle()

    # Schedule recurring runs
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_scrape_cycle,
        trigger=IntervalTrigger(hours=settings.scrape_interval_hours),
        id="scrape_cycle",
        name="Scrape all stores",
        replace_existing=True,
    )

    logger.info(f"Scheduler started: running every {settings.scrape_interval_hours} hours")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
