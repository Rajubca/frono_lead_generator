import requests
import json
import re
import shopify
from opensearchpy import OpenSearch, helpers
from config import (
    SHOPIFY_ACCESS_TOKEN,
    SHOPIFY_STORE_NAME,
    API_VERSION,
    OPENSEARCH_HOST
)
import time
from datetime import timedelta

# ---------------- INITIALIZATION ----------------
shopify.Session.setup(api_key=None, secret=None)
session = shopify.Session(
    f"{SHOPIFY_STORE_NAME}.myshopify.com",
    API_VERSION,
    SHOPIFY_ACCESS_TOKEN
)
shopify.ShopifyResource.activate_session(session)

os_client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": 9200}],
    http_compress=True
)

PRODUCT_INDEX = "frono_products"
FACTS_INDEX = "frono_site_facts"

# ---------------- HELPERS ----------------
def log_time(label, start):
    elapsed = time.time() - start
    print(f"⏱️ {label}: {timedelta(seconds=int(elapsed))} ({elapsed:.2f}s)")

def clean_html(raw_html):
    if not raw_html:
        return ""
    return re.sub(re.compile("<.*?>"), "", raw_html)


def fetch_collections_map():
    collections_map = {}
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    base = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}"

    def paginate(url):
        while url:
            res = requests.get(url, headers=headers)
            data = res.json()
            link = res.headers.get("Link")
            url = (
                re.findall(r'<(.*?)>; rel="next"', link)[0]
                if link and 'rel="next"' in link
                else None
            )
            yield data

    # 1️⃣ Fetch ALL collections
    collections = []
    for data in paginate(f"{base}/custom_collections.json?limit=250"):
        collections.extend(data.get("custom_collections", []))

    for data in paginate(f"{base}/smart_collections.json?limit=250"):
        collections.extend(data.get("smart_collections", []))

    # 2️⃣ Fetch ALL products per collection
    for col in collections:
        for data in paginate(f"{base}/collections/{col['id']}/products.json?limit=250"):
            for p in data.get("products", []):
                collections_map.setdefault(p["id"], []).append(col["title"])

    return collections_map


# ---------------- PRODUCT SYNC ----------------
def sync_all_products():
    total_start = time.time()
    print(f"--- 🚀 Starting Full Product Sync for {SHOPIFY_STORE_NAME} ---")

    collections_start = time.time()
    collections_map = fetch_collections_map()
    log_time("Collections map fetch", collections_start)


    # Existing SKUs (for cleanup)
    existing_skus = set()
    try:
        for hit in helpers.scan(
            os_client,
            index=PRODUCT_INDEX,
            query={"_source": ["sku"]}
        ):
            existing_skus.add(hit["_source"]["sku"])
    except Exception:
        pass

    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products.json?status=active&limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    actions = []
    active_skus = set()

    product_loop_start = time.time()
    while url:

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            break

        products = response.json().get("products", [])

        for product in products:
            category = product.get("product_type") or "General"

            # ✅ Shopify collections (dynamic, multi-valued)
            collections = collections_map.get(product["id"], [])
            if not collections:
                collections = ["Other"]

            raw_body = product.get("body_html") or ""
            clean_description = clean_html(raw_body[:500])

            for variant in product.get("variants", []):
                sku = variant.get("sku")
                if not sku:
                    continue

                qty = int(variant.get("inventory_quantity") or 0)
                active_skus.add(sku)

                actions.append({
                    "_op_type": "index",
                    "_index": PRODUCT_INDEX,
                    "_id": sku,
                    "_source": {
                        "sku": sku,
                        "name": product["title"],
                        "category": category,
                        "collection": collections,  # ✅ ARRAY
                        "price": float(variant["price"]),
                        "qty": qty,
                        "in_stock": qty > 0,
                        "description": clean_description,
                        "updated_at": product["updated_at"]
                    }
                })

        link = response.headers.get("Link")
        url = (
            re.findall(r'<(.*?)>; rel="next"', link)[0]
            if link and 'rel="next"' in link
            else None
        )
    log_time("Product fetch & action build", product_loop_start)


    # Cleanup deleted SKUs
    for sku in (existing_skus - active_skus):
        actions.append({
            "_op_type": "delete",
            "_index": PRODUCT_INDEX,
            "_id": sku
        })

    if actions:
        print(f"\n--- 💾 Executing {len(actions)} total actions ---")
        bulk_start = time.time()
        success, errors = helpers.bulk(
            os_client,
            actions,
            stats_only=False,
            raise_on_error=False
        )
        log_time("OpenSearch bulk execution", bulk_start)


        print(f"✅ Sync complete. {success} operations successful.")

        real_errors = [
            e for e in errors
            if list(e.values())[0].get("status") != 404
        ]
        if real_errors:
            print("❌ Actual failures:")
            print(json.dumps(real_errors, indent=2))
    log_time("Total product sync", total_start)


# ---------------- SITE FACTS SYNC ----------------
def sync_site_facts():
    total_start = time.time()
    print(f"--- 🌐 Starting Site Facts Sync ---")

    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    base = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}"
    actions = []

    # Pages
    pages = requests.get(f"{base}/pages.json", headers=headers).json().get("pages", [])
    for p in pages:
        actions.append({
            "_index": FACTS_INDEX,
            "_id": f"page_{p['id']}",
            "_source": {
                "type": "Page",
                "title": p["title"],
                "content": clean_html(p["body_html"]),
                "confidence": 100,
                "source": "Shopify"
            }
        })

    # Policies
    policies = requests.get(f"{base}/policies.json", headers=headers).json().get("policies", [])
    for pol in policies:
        actions.append({
            "_index": FACTS_INDEX,
            "_id": f"policy_{pol['title'].lower()}",
            "_source": {
                "type": "Policy",
                "title": pol["title"],
                "content": clean_html(pol.get("body") or pol.get("body_html")),
                "confidence": 100,
                "source": "Shopify"
            }
        })

    helpers.bulk(os_client, actions)
    log_time("Site facts sync", total_start)

    print("✅ Site Facts Updated.")


# ---------------- ENTRY ----------------
if __name__ == "__main__":
    script_start = time.time()
    sync_all_products()
    sync_site_facts()
    log_time("TOTAL SCRIPT EXECUTION", script_start)
