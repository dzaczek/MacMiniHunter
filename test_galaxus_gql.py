"""Find Galaxus GraphQL API and extract products."""
import json
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()
s.headers["Accept-Encoding"] = "gzip, deflate"

# Get the search page
r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"HTTP {r.status_code}")

nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
if not nd:
    print("No __NEXT_DATA__")
    sys.exit(1)

data = json.loads(nd.group(1))

# Analyze __NEXT_DATA__ structure
print(f"Top keys: {list(data.keys())}")
print(f"Build ID: {data.get('buildId')}")
props = data.get("props", {})
print(f"Props keys: {list(props.keys())}")
pp = props.get("pageProps", {})
print(f"PageProps keys: {list(pp.keys())}")

# Look for Relay environment or query info
for key in props:
    val = props[key]
    if isinstance(val, dict):
        text = json.dumps(val)[:500]
        if "query" in text.lower() or "graphql" in text.lower() or "relay" in text.lower():
            print(f"\nprops.{key}: {text[:300]}")

# Check pageProps deeper
for key in pp:
    val = pp[key]
    if isinstance(val, (dict, list)):
        text = json.dumps(val)[:200]
        print(f"\npageProps.{key}: {text}")

# Save full __NEXT_DATA__ for analysis
print(f"\n\nFull __NEXT_DATA__ size: {len(json.dumps(data))}")
print(f"Full dump (first 3000):\n{json.dumps(data, indent=2)[:3000]}")

# Find JS chunks that contain GraphQL query definitions
print("\n\n" + "=" * 60)
print("Looking for GraphQL in JS chunks")
print("=" * 60)

scripts = re.findall(r'src="(/_next/static/[^"]+\.js)"', r.text)
print(f"JS chunks: {len(scripts)}")

# Find the search-related chunk
for script_url in scripts[:10]:
    full_url = f"https://www.galaxus.ch{script_url}"
    try:
        js = s.get(full_url, timeout=10)
        if js.status_code == 200:
            text = js.text
            # Look for search query operations
            if "search" in text.lower() and ("graphql" in text.lower() or "query" in text.lower() or "relay" in text.lower()):
                # Find operation names
                ops = re.findall(r'operationName["\s:]+["\'](\w+)["\']', text)
                search_ops = [op for op in ops if "search" in op.lower() or "product" in op.lower()]
                if search_ops:
                    print(f"\n{script_url}: search ops = {search_ops}")

                # Find persisted query hashes
                hashes = re.findall(r'"([a-f0-9]{64})"', text)
                if hashes and search_ops:
                    print(f"  Hashes: {hashes[:3]}")

                # Find GraphQL endpoint
                endpoints = re.findall(r'"(/graphql[^"]*)"', text)
                if endpoints:
                    print(f"  Endpoints: {endpoints[:3]}")
    except:
        pass

# Try the GraphQL endpoint directly
print("\n\n" + "=" * 60)
print("Trying GraphQL endpoints")
print("=" * 60)

gql_endpoints = [
    "https://www.galaxus.ch/graphql",
    "https://www.galaxus.ch/api/graphql",
    "https://www.galaxus.ch/api/graphql/search",
]

for endpoint in gql_endpoints:
    # Introspection query
    payload = {
        "query": '{ __schema { queryType { name } } }',
    }
    try:
        gr = s.post(endpoint, json=payload, timeout=10, headers={
            "Content-Type": "application/json",
            "Origin": "https://www.galaxus.ch",
            "Referer": "https://www.galaxus.ch/en/search?q=mac+mini",
        })
        print(f"\n{endpoint}: HTTP {gr.status_code}")
        print(f"  Body: {gr.text[:500]}")
    except Exception as e:
        print(f"\n{endpoint}: {e}")

# Try search query
search_payload = [{
    "operationName": "SEARCH_PRODUCTS",
    "variables": {"searchTerm": "mac mini", "offset": 0, "limit": 24},
    "query": "query SEARCH_PRODUCTS($searchTerm: String!) { search(searchTerm: $searchTerm) { products { name } } }"
}]

try:
    gr2 = s.post("https://www.galaxus.ch/api/graphql", json=search_payload, timeout=10, headers={
        "Content-Type": "application/json",
        "Origin": "https://www.galaxus.ch",
        "Referer": "https://www.galaxus.ch/en/search?q=mac+mini",
    })
    print(f"\nSearch query: HTTP {gr2.status_code}")
    print(f"  Body: {gr2.text[:500]}")
except Exception as e:
    print(f"\nSearch query: {e}")
