"""Extract full product data from Fust RSC."""
import json
import re
import requests

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-CH,de;q=0.9",
})

# Use the category page that works
url = "https://www.fust.ch/handy-pc-tablet/pc-computer-monitore/mac-mini-mac-studio/c/f_mac_mini_mac_studio"
r = session.get(url, timeout=30)

if r.status_code != 200:
    print(f"Failed: HTTP {r.status_code}")
    exit(1)

html = r.text

# Extract and combine RSC data
rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.DOTALL)
combined = "".join(rsc_chunks)
# Unescape JSON-escaped strings
combined = combined.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/').replace('\\\\', '\\')

# Find the product array we saw earlier
# It starts with "products":[{...
products_match = re.search(r'"products"\s*:\s*\[(.*?)\]\s*[,}]', combined, re.DOTALL)
if products_match:
    products_json = "[" + products_match.group(1) + "]"
    try:
        products = json.loads(products_json)
        print(f"Found {len(products)} products!")
        for p in products:
            name = p.get("name", "?")
            brand = p.get("brandName", "?")
            avail = p.get("availability", {})
            print(f"\n  Product: {brand} {name}")
            print(f"  Delivery: {avail.get('deliveryStatus')}")
            print(f"  Stock: {avail.get('stockLevel')}")
            # Find price - check various fields
            price = p.get("price") or p.get("salesPrice") or p.get("currentPrice")
            if price:
                print(f"  Price: {price}")
            # Check for price in nested objects
            for key in ["pricing", "prices", "priceData", "productPrice"]:
                if key in p:
                    print(f"  {key}: {p[key]}")
            # Print all keys
            print(f"  Keys: {list(p.keys())}")
            # Print full product
            print(f"  Full: {json.dumps(p)[:500]}")
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        # Try to extract individual product objects
        individual = re.findall(r'\{[^{}]*"name"[^{}]*\}', products_json)
        print(f"Individual product objects: {len(individual)}")
        for ind in individual[:3]:
            print(f"  {ind[:300]}")

# Also search for price patterns in the full RSC data
# Look for price near product names
for m in re.finditer(r'"name"\s*:\s*"(Mac Mini[^"]*)"', combined, re.IGNORECASE):
    name = m.group(1)
    # Search in wider context
    start = max(0, m.start() - 1000)
    end = min(len(combined), m.end() + 1000)
    context = combined[start:end]

    # Find any price-related data
    price_patterns = [
        r'"price"\s*:\s*"?([\d.]+)"?',
        r'"formattedPrice"\s*:\s*"([^"]+)"',
        r'"displayPrice"\s*:\s*"([^"]+)"',
        r'"salesPrice"\s*:\s*"?([\d.]+)"?',
        r'"value"\s*:\s*"?([\d.]+)"?',
        r'CHF\s*([\d.]+)',
    ]
    found_price = False
    for pp in price_patterns:
        pm = re.search(pp, context)
        if pm:
            print(f"\n{name} -> {pp}: {pm.group(1)}")
            found_price = True
    if not found_price:
        print(f"\n{name} -> NO PRICE FOUND in context")

# Try a completely different approach: Fust search API
# Some sites have an internal search API used by the frontend
print("\n\n" + "=" * 60)
print("Trying Fust internal APIs")
print("=" * 60)

api_patterns = [
    "https://www.fust.ch/api/v1/search?q=mac+mini&lang=de",
    "https://www.fust.ch/_next/data/{buildId}/de/search.json?q=mac+mini",
    "https://www.fust.ch/de/search.json?q=mac+mini",
]

# Find the build ID from RSC data
build_id_match = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
if build_id_match:
    bid = build_id_match.group(1)
    print(f"Build ID: {bid}")
    api_patterns.append(f"https://www.fust.ch/_next/data/{bid}/de/search.json?q=mac+mini")

# Also look for hybris/SAP Commerce API endpoints (Fust uses SAP Commerce)
api_patterns.extend([
    "https://www.fust.ch/fustapi/v2/fust-ch/products/search?query=mac+mini&lang=de",
    "https://www.fust.ch/fustapi/products/search?query=mac+mini",
    "https://api.fust.ch/products/search?q=mac+mini",
])

for api_url in api_patterns:
    try:
        ar = session.get(api_url, timeout=10)
        print(f"\n{api_url}")
        print(f"  HTTP {ar.status_code}, size={len(ar.text)}")
        if ar.status_code == 200 and len(ar.text) > 100:
            ct = ar.headers.get("content-type", "")
            if "json" in ct:
                data = ar.json()
                print(f"  JSON keys: {list(data.keys()) if isinstance(data, dict) else 'array'}")
                print(f"  Preview: {json.dumps(data)[:500]}")
            else:
                print(f"  Content-Type: {ct}")
                if "mac" in ar.text.lower():
                    print(f"  Contains 'mac'!")
    except Exception as e:
        print(f"\n{api_url}: {e}")
