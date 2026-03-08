"""Try Galaxus Apollo /api/graphql with correct query names."""
import json
import re
import sys
import time
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()
s.headers["Accept-Encoding"] = "gzip, deflate"

# Step 1: Get search page + cookies
print("Step 1: Get search page...")
r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"HTTP {r.status_code}")

if r.status_code != 200:
    print("Blocked. Trying with fresh session...")
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-CH,en;q=0.9",
    })
    r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
    print(f"Retry: HTTP {r.status_code}")
    if r.status_code != 200:
        sys.exit(1)

# Step 2: Try /api/graphql with various query names
print("\nStep 2: Try /api/graphql...")

headers = {
    "Content-Type": "application/json",
    "Origin": "https://www.galaxus.ch",
    "Referer": "https://www.galaxus.ch/en/search?q=mac+mini",
    "Accept": "*/*",
}

# Discovery: try __typename to verify API is working
test_q = [{"query": "{ __typename }"}]
tr = s.post("https://www.galaxus.ch/api/graphql", json=test_q, headers=headers, timeout=10)
print(f"__typename: HTTP {tr.status_code}, body: {tr.text[:200]}")

if tr.status_code != 200:
    print("API blocked too")
    sys.exit(1)

# If __typename works, the API is accessible. Try to find valid query fields.
# Test various root query field names
field_names = [
    "search", "productSearch", "searchProducts", "products", "productListing",
    "catalog", "searchPage", "productList", "browseSearch", "filteredProducts",
    "searchResults", "productResults", "queryProducts", "findProducts",
]

for field in field_names:
    q = [{"query": f'{{ {field}(query: "mac mini") {{ __typename }} }}'}]
    try:
        fr = s.post("https://www.galaxus.ch/api/graphql", json=q, headers=headers, timeout=5)
        body = fr.text
        if "Cannot query field" in body:
            # Check for suggestions
            suggestion = re.search(r'Did you mean "([^"]+)"', body)
            if suggestion:
                print(f"  {field} -> suggested: {suggestion.group(1)}")
        elif "VALIDATION_FAILED" not in body and fr.status_code == 200:
            print(f"  {field} -> WORKS! Status: {fr.status_code}")
            print(f"    Body: {body[:300]}")
    except:
        pass

# Also try without arguments
for field in ["search", "products", "allProducts", "catalog"]:
    q = [{"query": f"{{ {field} {{ __typename }} }}"}]
    try:
        fr = s.post("https://www.galaxus.ch/api/graphql", json=q, headers=headers, timeout=5)
        body = fr.text
        if "Cannot query field" not in body and "VALIDATION_FAILED" not in body:
            print(f"  {field} (no args) -> {fr.status_code}: {body[:200]}")
    except:
        pass

# Try known Digitec/Galaxus query patterns from their React codebase
print("\nTrying known Digitec patterns...")
known_queries = [
    # Product type listing
    [{"operationName": "GET_PRODUCT_TYPE_PRODUCTS",
      "variables": {"productTypeId": 220, "queryString": "mac mini", "offset": 0, "limit": 24, "siteId": None, "sortOrder": None, "sectorId": None},
      "query": "query GET_PRODUCT_TYPE_PRODUCTS($productTypeId: Int!, $queryString: String, $offset: Int, $limit: Int) { productType(id: $productTypeId) { filterProductsV4(queryString: $queryString, offset: $offset, limit: $limit) { products { nodes { productId name brandName currentOffer { id price { amountIncl currency } } } } } } }"}],

    # Monolith search
    [{"operationName": "SEARCH_SUGGEST",
      "variables": {"searchTerm": "mac mini"},
      "query": "query SEARCH_SUGGEST($searchTerm: String!) { searchSuggestions(searchTerm: $searchTerm) { suggestions { title } products { name brandName currentOffer { price { amountIncl } } pdpUrl } } }"}],
]

for kq in known_queries:
    try:
        kr = s.post("https://www.galaxus.ch/api/graphql", json=kq, headers=headers, timeout=10)
        name = kq[0].get("operationName", "?")
        body = kr.text
        print(f"\n  {name}: HTTP {kr.status_code}")
        if "Cannot query field" in body:
            suggestions = re.findall(r'Did you mean "([^"]+)"', body)
            if suggestions:
                print(f"    Suggestions: {suggestions}")
        else:
            print(f"    Body: {body[:500]}")
    except Exception as e:
        print(f"  Error: {e}")
