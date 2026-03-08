"""Live integration test - runs all scrapers and reports results."""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

sys.path.insert(0, ".")

from src.scrapers.brack import BrackScraper
from src.scrapers.fust import FustScraper
from src.scrapers.apple import AppleScraper
from src.scrapers.ricardo import RicardoScraper

SCRAPERS = [
    ("BRACK (JSON-LD)", BrackScraper),
    ("FUST (RSC)", FustScraper),
    ("APPLE STORE CH", AppleScraper),
    ("RICARDO (Playwright)", RicardoScraper),
]

total = 0
for name, cls in SCRAPERS:
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    scraper = cls()
    results = scraper.run()
    count = len(results)
    total += count
    print(f"{name}: {count} results")

    for r in results[:5]:
        avail = "In Stock" if r.availability else "Out of Stock"
        print(f"  CHF {r.price_chf:8.2f} - {r.title[:70]} [{avail}]")

    if count > 5:
        print(f"  ... and {count - 5} more")

print(f"\n{'='*60}")
print(f"TOTAL: {total} results from all scrapers")
print(f"{'='*60}")
