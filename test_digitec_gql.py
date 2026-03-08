"""Try to call Digitec's GraphQL gateway with persisted query format."""
import re
import json
import sys
sys.path.insert(0, ".")

from src.utils.stealth import create_session

s = create_session()

# First get the search page to extract any relay query details
r = s.get("https://www.digitec.ch/de/search?q=mac+mini", timeout=30)
nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
data = json.loads(nd_match.group(1))

# Get the preloaded layout query params
preloaded = data.get("props", {}).get("preloadedLayoutQuery", {})
params = preloaded.get("params", {})
print(f"Relay params: {json.dumps(params, indent=2)[:500]}")

relay_vars = preloaded.get("variables", {})
print(f"Relay variables: {json.dumps(relay_vars, indent=2)[:500]}")

# Get the query ID
query_id = params.get("id") or params.get("name", "")
print(f"Query ID/Name: {query_id}")

# Try calling the gateway
gql_url = "https://www.digitec.ch/graphql"

# Standard Relay persisted query format
headers = {
    "Content-Type": "application/json",
    "Referer": "https://www.digitec.ch/de/search?q=mac+mini",
    "Origin": "https://www.digitec.ch",
    "Accept": "*/*",
}
s.headers.update(headers)

# Try the persisted query format
payload = {
    "id": query_id,
    "variables": relay_vars,
}

try:
    resp = s.post(gql_url, json=payload, timeout=15)
    print(f"\nGQL response: {resp.status_code}")
    print(f"Body: {resp.text[:1000]}")
except Exception as e:
    print(f"GQL error: {e}")

# Also try with extensions format (Apollo-style persisted queries)
payload2 = {
    "operationName": params.get("name", ""),
    "variables": relay_vars,
    "extensions": {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": query_id,
        }
    }
}

try:
    resp = s.post(gql_url, json=payload2, timeout=15)
    print(f"\nGQL v2 response: {resp.status_code}")
    print(f"Body: {resp.text[:1000]}")
except Exception as e:
    print(f"GQL v2 error: {e}")

# Try /api/graphql endpoint (monolith)
page_props = data.get("props", {}).get("pageProps", {})
variables = page_props.get("variables", {})
search_query_id = variables.get("searchQueryConfig", {}).get("searchQueryId", "")

# Digitec monolith search query
mono_payload = {
    "query": "",
    "operationName": "SEARCH_PRODUCTS_QUERY",
    "variables": {
        "query": "mac mini",
        "limit": 24,
        "offset": 0,
    }
}

try:
    resp = s.post("https://www.digitec.ch/api/graphql", json=mono_payload, timeout=15)
    print(f"\nMonolith response: {resp.status_code}")
    print(f"Body: {resp.text[:500]}")
except Exception as e:
    print(f"Monolith error: {e}")

# Try with the search query from page props
mono_payload2 = [{
    "operationName": "GET_PRODUCT_LISTING",
    "variables": {
        "productIds": [],
        "filters": [],
        "searchTerm": "mac mini",
        "sort": "BESTSELLER",
        "take": 24,
        "skip": 0,
    },
    "query": ""
}]

try:
    resp = s.post("https://www.digitec.ch/api/graphql", json=mono_payload2, timeout=15)
    print(f"\nMonolith v2: {resp.status_code}")
    print(f"Body: {resp.text[:500]}")
except Exception as e:
    print(f"Monolith v2 error: {e}")
