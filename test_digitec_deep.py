"""Deep Digitec analysis - find persisted query IDs and search API."""
import re
import json
import sys
sys.path.insert(0, ".")

from src.utils.stealth import create_session

s = create_session()
r = s.get("https://www.digitec.ch/de/search?q=mac+mini", timeout=30)

if r.status_code != 200:
    print(f"HTTP {r.status_code}")
    sys.exit(1)

nd_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text)
if not nd_match:
    print("No __NEXT_DATA__")
    sys.exit(1)

data = json.loads(nd_match.group(1))

# Look at page props - search config
page_props = data.get("props", {}).get("pageProps", {})
print("pageProps keys:", list(page_props.keys()))

# Look for query/search variables
variables = page_props.get("variables", {})
print(f"variables: {json.dumps(variables, indent=2)[:1000]}")

# Look for preloaded queries with IDs
for key in data.get("props", {}):
    val = data["props"][key]
    if isinstance(val, dict) and "id" in str(val)[:500]:
        text = json.dumps(val)
        ids = re.findall(r'"id"\s*:\s*"([a-f0-9]{20,})"', text)
        if ids:
            print(f"Query IDs in props.{key}: {ids[:5]}")

# Find all JS chunk URLs to locate the GraphQL queries
scripts = re.findall(r'src="(/_next/static/[^"]+\.js)"', r.text)
print(f"\nFound {len(scripts)} JS chunks")

# Try to find the search query in the first few chunks
for script_url in scripts[:5]:
    full_url = f"https://www.digitec.ch{script_url}"
    try:
        js_resp = s.get(full_url, timeout=10)
        if js_resp.status_code == 200:
            js_text = js_resp.text
            # Look for GraphQL operation names related to search
            ops = re.findall(r'operationName["\s:]+["\']([\w]+)["\']', js_text)
            if any("search" in op.lower() for op in ops):
                print(f"\nSearch-related ops in {script_url}:")
                for op in ops:
                    if "search" in op.lower() or "product" in op.lower():
                        print(f"  {op}")

            # Look for persisted query hashes
            hashes = re.findall(r'"([a-f0-9]{64})"', js_text)
            if hashes:
                print(f"  Persisted hashes: {hashes[:3]}")
    except Exception:
        pass

# Try the GraphQL gateway with search query from __NEXT_DATA__
config = data.get("props", {}).get("clientConfig", {})
gql_config = config.get("graphql", {})
print(f"\nGraphQL config: {json.dumps(gql_config, indent=2)}")

# Try the graphql gateway
gql_url = f"https://www.digitec.ch{gql_config.get('graphqlGateway', '/graphql')}"
print(f"Gateway URL: {gql_url}")

# Look at relay store for preloaded data
relay_env = data.get("props", {}).get("preloadedLayoutQuery", {})
print(f"\npreloadedLayoutQuery keys: {list(relay_env.keys()) if isinstance(relay_env, dict) else 'not a dict'}")

search_config = page_props.get("searchQueryConfig", variables.get("searchQueryConfig", {}))
print(f"\nsearchQueryConfig: {json.dumps(search_config, indent=2)[:500]}")
