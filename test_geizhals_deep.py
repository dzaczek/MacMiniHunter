"""Deep dive into Geizhals to extract all Mac Mini products and prices."""
import json
import re
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9",
})

# Geizhals Mac Mini category - filter for Swiss shops
# Cat: Desktop PCs / Nettops
url = "https://geizhals.ch/?cat=sysdiv&xf=21862_Apple+Mac+mini&hloc=ch&v=l"
r = session.get(url, timeout=30)
print(f"HTTP {r.status_code}, size={len(r.text)}")

if r.status_code != 200:
    exit(1)

html = r.text

# Geizhals uses list view (v=l) - extract product rows
# Pattern: product-id, name, price
product_blocks = re.findall(
    r'<div[^>]+data-product-id="(\d+)"[^>]*>(.*?)</div>\s*</div>\s*</div>',
    html, re.DOTALL
)
print(f"Product blocks with data-product-id: {len(product_blocks)}")

# Try alternative: look at the full list view structure
# Get all product IDs
pids = re.findall(r'data-product-id="(\d+)"', html)
print(f"Product IDs: {pids}")

# Get product detail: for each product, find name, price, and offers count
# Geizhals list view structure:
#   .listview__row > .listview__name > a.listview__name-link
#   .listview__row > .listview__price > span

# Find all product entries using name links
name_pattern = r'class="[^"]*listview__name[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
names = re.findall(name_pattern, html)
print(f"\nProduct names (listview): {len(names)}")
for href, name in names:
    print(f"  {name.strip()}: https://geizhals.ch/{href}")

# Try gallery view pattern
gallery_pattern = r'class="galleryview__name"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"'
gallery_names = re.findall(gallery_pattern, html)
print(f"\nProduct names (galleryview): {len(gallery_names)}")
for href, name in gallery_names:
    print(f"  {name.strip()}: https://geizhals.ch/{href}")

# Find prices associated with products
price_pattern = r'class="[^"]*price[^"]*"[^>]*>\s*(?:ab\s*)?(?:CHF\s*)?(&euro;|€)?\s*([\d\.,]+)'
price_matches = re.findall(price_pattern, html)
print(f"\nPrice elements: {len(price_matches)}")
for curr, price in price_matches[:20]:
    print(f"  {curr or 'CHF'} {price}")

# Let's try getting a product detail page to see the shop-level offers
if pids:
    # Try the first Mac Mini product
    detail_url = f"https://geizhals.ch/a{pids[-1]}.html"  # Last one is most likely Mac Mini
    print(f"\n\nFetching detail page: {detail_url}")
    r2 = session.get(detail_url, timeout=15)
    print(f"HTTP {r2.status_code}")
    if r2.status_code == 200:
        dhtml = r2.text
        # Product title
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', dhtml, re.DOTALL)
        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
            print(f"Product: {title}")

        # Offers from different shops
        # Geizhals shows offers in #offerlist
        offers = re.findall(
            r'<span[^>]*class="[^"]*shopName[^"]*"[^>]*>(.*?)</span>.*?'
            r'class="[^"]*offerList__price[^"]*"[^>]*>\s*(?:CHF\s*)?([\d\.,]+)',
            dhtml, re.DOTALL
        )
        print(f"\nShop offers: {len(offers)}")
        for shop, price in offers[:15]:
            shop_clean = re.sub(r'<[^>]+>', '', shop).strip()
            print(f"  {shop_clean}: CHF {price}")

        # Alternative offer pattern
        offer_rows = re.findall(
            r'data-shop-name="([^"]+)".*?'
            r'class="[^"]*variant__header__price[^"]*"[^>]*>\s*(?:CHF\s*)?([\d\.,]+)',
            dhtml, re.DOTALL
        )
        print(f"\nAlternative offer pattern: {len(offer_rows)}")
        for shop, price in offer_rows[:15]:
            print(f"  {shop}: CHF {price}")

        # Try yet another pattern
        offer_blocks = re.findall(
            r'<tr[^>]*class="[^"]*offer[^"]*"[^>]*>.*?</tr>',
            dhtml, re.DOTALL
        )
        print(f"\nOffer table rows: {len(offer_blocks)}")
        for block in offer_blocks[:3]:
            # Extract shop name
            shop_match = re.search(r'class="[^"]*shopname[^"]*"[^>]*>([^<]+)', block, re.IGNORECASE)
            price_match = re.search(r'([\d\',.]+)\s*(?:CHF)?', block)
            if shop_match:
                print(f"  Shop: {shop_match.group(1).strip()}, Price in block: {price_match.group(1) if price_match else '?'}")

        # Find all offer data in any format
        # Save relevant HTML chunk
        offer_section = re.search(r'id="offerlist"(.*?)id="footer"', dhtml, re.DOTALL)
        if offer_section:
            osec = offer_section.group(1)
            print(f"\nOffer section length: {len(osec)}")
            # Find shop-price pairs
            shop_price_pairs = re.findall(
                r'(?:data-shop-name|class="[^"]*shopn)[^>]*>?\s*"?([^"<]+)"?\s*<.*?'
                r'(?:CHF|Fr\.?)\s*([\d\',.]+)',
                osec, re.DOTALL
            )
            print(f"Shop-price pairs: {len(shop_price_pairs)}")
            for shop, price in shop_price_pairs[:10]:
                print(f"  {shop.strip()}: CHF {price}")

        # Raw offer list HTML sample
        print("\n--- Raw HTML sample from offer area ---")
        if offer_section:
            print(offer_section.group(1)[:2000])

# Also try the list view URL with Mac Mini filter
print("\n\n" + "=" * 60)
print("Trying direct Mac Mini category filter")
list_url = "https://geizhals.ch/?cat=sysdiv&xf=21862_Apple+Mac+mini&hloc=ch&v=l&sort=p"
r3 = session.get(list_url, timeout=30)
print(f"HTTP {r3.status_code}")
if r3.status_code == 200:
    # Find all visible product entries
    # Pattern: product link + price on same row
    entries = re.findall(
        r'href="([^"]*a\d+\.html[^"]*)"[^>]*>\s*([^<]+Mac[^<]*mini[^<]*)</a>',
        r3.text, re.IGNORECASE
    )
    print(f"\nMac Mini product links: {len(entries)}")
    for href, name in entries:
        print(f"  {name.strip()}")
