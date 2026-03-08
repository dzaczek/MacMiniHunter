"""Try Galaxus Relay persisted queries to get search results."""
import json
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()
s.headers["Accept-Encoding"] = "gzip, deflate"

# Get search page to extract query config
r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"HTTP {r.status_code}, size={len(r.text)}")
nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
if not nd:
    print("No __NEXT_DATA__ found")
    print(f"Body preview: {r.text[:500]}")
    sys.exit(1)
data = json.loads(nd.group(1))

pp = data["props"]["pageProps"]
gql_opts = data["props"]["graphQLOptions"]
search_vars = pp["variables"]

print(f"Search variables: {json.dumps(search_vars)}")
print(f"GraphQL options: {json.dumps(gql_opts)}")

# Try the /api/graphql endpoint with a search-like query
# Galaxus uses Apollo on /api/graphql
# Let's try common operation names

headers = {
    "Content-Type": "application/json",
    "Origin": "https://www.galaxus.ch",
    "Referer": "https://www.galaxus.ch/en/search?q=mac+mini",
    "x-portalid": str(gql_opts.get("portalId", 22)),
    "x-experimentation-id": gql_opts.get("experimentationId", ""),
}

# Try various operation names that might work
operations = [
    {
        "operationName": "GET_PRODUCT_LISTING",
        "variables": {
            "productIds": [],
            "query": "mac mini",
            "offset": 0,
            "limit": 24,
        },
        "query": "query GET_PRODUCT_LISTING($query: String!, $offset: Int, $limit: Int) { productListing(query: $query, offset: $offset, limit: $limit) { products { productId name currentOffer { price { amountIncl } } url } } }",
    },
    {
        "operationName": "SearchProducts",
        "variables": {
            "query": "mac mini",
            "limit": 24,
        },
        "query": "query SearchProducts($query: String!, $limit: Int) { searchProducts(query: $query, limit: $limit) { products { productId name brandName currentOffer { price { amountIncl } } pdpUrl } totalCount } }",
    },
    {
        "operationName": "PRL_PRODUCTS",
        "variables": {
            "queryString": "mac mini",
            "limit": 24,
            "offset": 0,
        },
        "query": "query PRL_PRODUCTS($queryString: String!, $limit: Int!, $offset: Int!) { search(queryString: $queryString) { products(limit: $limit, offset: $offset) { productId name brandName price { amountIncl } url } } }",
    },
]

for op in operations:
    try:
        gr = s.post("https://www.galaxus.ch/api/graphql", json=[op], headers=headers, timeout=10)
        print(f"\n{op['operationName']}: HTTP {gr.status_code}")
        body = gr.text[:500]
        print(f"  Body: {body}")
        if gr.status_code == 200 and "product" in body.lower():
            print("  *** HAS PRODUCTS! ***")
    except Exception as e:
        print(f"\n{op['operationName']}: {e}")

# Try the gateway with persisted query format
print("\n\n" + "=" * 60)
print("Gateway persisted queries")
print("=" * 60)

# The layout query ID from __NEXT_DATA__
layout_query = data["props"]["preloadedLayoutQuery"]
print(f"Layout query ID: {layout_query['params']['id']}")
print(f"Layout query name: {layout_query['params']['name']}")

# Try the gateway with layout query
gw_payload = {
    "id": layout_query["params"]["id"],
    "variables": layout_query["variables"],
}

try:
    gr2 = s.post("https://www.galaxus.ch/graphql", json=gw_payload, headers=headers, timeout=10)
    print(f"\nGateway layout: HTTP {gr2.status_code}")
    print(f"  Body: {gr2.text[:500]}")
except Exception as e:
    print(f"\nGateway layout: {e}")

# Try to find the search query ID from JS chunks
# The page has no <script src=...> tags because it's SSR with inline scripts
# Let's look at the apolloState for pre-loaded data
apollo_state = data["props"].get("apolloState")
if apollo_state:
    print(f"\napolloState keys: {list(apollo_state.keys())[:20]}")
    # Walk for products
    found = []
    for key, val in apollo_state.items():
        if isinstance(val, dict):
            name = val.get("name") or val.get("productName") or ""
            if "mac" in str(name).lower() and "mini" in str(name).lower():
                found.append({"key": key, "data": val})
    print(f"Mac Mini in apolloState: {len(found)}")
    for f in found[:5]:
        print(f"  {f['key']}: {json.dumps(f['data'])[:300]}")
else:
    print("\nNo apolloState")

# Check relayEnvironment
relay_env = data["props"].get("relayEnvironment")
if relay_env:
    text = json.dumps(relay_env)
    print(f"\nrelayEnvironment (first 500): {text[:500]}")
    # Look for product data
    if "mac" in text.lower():
        print("  Contains 'mac'!")

# Last resort: try the buildId-based data fetching
build_id = data.get("buildId")
if build_id:
    data_url = f"https://www.galaxus.ch/_next/data/{build_id}/en/search.json?q=mac+mini"
    try:
        dr = s.get(data_url, timeout=10)
        print(f"\n_next/data: HTTP {dr.status_code}, size={len(dr.text)}")
        if dr.status_code == 200:
            d = dr.json()
            print(f"  Keys: {list(d.keys()) if isinstance(d, dict) else 'not dict'}")
            print(f"  Preview: {json.dumps(d)[:500]}")
    except Exception as e:
        print(f"\n_next/data: {e}")
