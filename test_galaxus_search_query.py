"""Find the Galaxus search Relay query ID by analyzing the client-side JS."""
import json
import re
import sys
sys.path.insert(0, ".")
from src.utils.stealth import create_session

s = create_session()
s.headers["Accept-Encoding"] = "gzip, deflate"

# Get the search page HTML to find JS bundle URLs
r = s.get("https://www.galaxus.ch/en/search?q=mac+mini", timeout=30)
print(f"HTTP {r.status_code}, size={len(r.text)}")

# Find all script sources (both inline and external)
# Galaxus uses Next.js with script tags
script_srcs = re.findall(r'src="([^"]+\.js[^"]*)"', r.text)
print(f"Script sources: {len(script_srcs)}")

# Also find inline scripts that might contain relay query IDs
inline_scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
print(f"Inline scripts: {len(inline_scripts)}")

# Look for Relay query IDs in inline scripts
for i, script in enumerate(inline_scripts):
    if len(script) < 50:
        continue
    # Find 32-char hex strings (Relay persisted query IDs)
    hex_ids = re.findall(r'"([a-f0-9]{32})"', script)
    if hex_ids:
        print(f"\nInline script {i} (len={len(script)}): hex IDs = {hex_ids[:5]}")
        # Check if it has search-related content
        if "search" in script.lower():
            print(f"  Contains 'search'!")
            # Find the context around the ID
            for hid in hex_ids:
                pos = script.find(hid)
                if pos >= 0:
                    ctx = script[max(0,pos-100):pos+150]
                    print(f"  Context for {hid}: ...{ctx}...")

# Look for JS chunks that reference search
search_scripts = []
for src in script_srcs:
    if "search" in src.lower() or "chunk" in src.lower():
        search_scripts.append(src)

print(f"\nSearch-related scripts: {len(search_scripts)}")
for src in search_scripts[:5]:
    print(f"  {src}")

# Download and search the main/webpack chunks for search query
# Focus on chunks that are likely to contain the search query
for src in script_srcs[:15]:
    url = src if src.startswith("http") else f"https://www.galaxus.ch{src}"
    try:
        jr = s.get(url, timeout=10)
        if jr.status_code != 200:
            continue
        js = jr.text
        if len(js) < 100:
            continue

        # Look for persisted query IDs with search context
        # Pattern: id:"hexhash",name:"SomeSearchQuery"
        query_defs = re.findall(r'id\s*:\s*"([a-f0-9]{32,64})"\s*,\s*(?:metadata[^,]*,\s*)?name\s*:\s*"([^"]+)"', js)
        if query_defs:
            search_defs = [(qid, name) for qid, name in query_defs if "search" in name.lower() or "product" in name.lower()]
            if search_defs:
                print(f"\n{src.split('/')[-1]}:")
                for qid, name in search_defs:
                    print(f"  Query: {name} = {qid}")

        # Also look for operation names
        if "search" in js.lower() and "operationKind" in js:
            ops = re.findall(r'name\s*:\s*"([^"]*search[^"]*)"', js, re.IGNORECASE)
            if ops:
                print(f"\n{src.split('/')[-1]}: search operations = {ops[:10]}")

    except Exception as e:
        continue

# Also try to use the Apollo /api/graphql endpoint which accepts arbitrary queries
# Maybe we can discover the right schema
print("\n\n" + "=" * 60)
print("Apollo schema discovery")
print("=" * 60)

headers = {
    "Content-Type": "application/json",
    "Origin": "https://www.galaxus.ch",
    "Referer": "https://www.galaxus.ch/en/search?q=mac+mini",
}

# Try to list root query fields
discovery_queries = [
    {"query": "{ __type(name: \"Query\") { fields { name } } }"},
    {"query": "query { productSearch(query: \"mac mini\") { products { name } } }"},
    {"query": "query { productListing(searchQuery: \"mac mini\") { products { name } } }"},
    {"query": "query { products(search: \"mac mini\") { name } }"},
    {"query": "query { search(query: \"mac mini\") { products { name } } }"},
]

for dq in discovery_queries:
    try:
        dr = s.post("https://www.galaxus.ch/api/graphql", json=[dq], headers=headers, timeout=10)
        body = dr.text[:300]
        if "VALIDATION_FAILED" not in body and "introspection" not in body.lower():
            print(f"\n  Query: {dq['query'][:80]}")
            print(f"  HTTP {dr.status_code}: {body}")
        elif "Cannot query field" in body:
            # Extract the suggestion if any
            suggestion = re.search(r'Did you mean "([^"]+)"', body)
            if suggestion:
                print(f"\n  Suggestion for {dq['query'][:50]}: {suggestion.group(1)}")
    except:
        pass
