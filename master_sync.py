import requests
import json
import re
from opensearchpy import OpenSearch, helpers
from config import (
    SHOPIFY_ACCESS_TOKEN, 
    SHOPIFY_STORE_NAME, 
    API_VERSION, 
    OPENSEARCH_HOST
)

# --- INITIALIZATION ---
os_client = OpenSearch(hosts=[{'host': OPENSEARCH_HOST, 'port': 9200}], http_compress=True)
PRODUCT_INDEX = "frono_products"
FACTS_INDEX = "frono_site_facts"

def clean_html(raw_html):
    if not raw_html: return ""
    return re.sub(re.compile('<.*?>'), '', raw_html)

# --- 1. PAGINATED PRODUCT SYNC ---
def sync_all_products():
    print(f"--- 🚀 Starting Full Product Sync for {SHOPIFY_STORE_NAME} ---")
    
    # Get current SKUs for cleanup
    existing_skus = set()
    try:
        for hit in helpers.scan(os_client, index=PRODUCT_INDEX, query={"_source": ["sku"]}):
            existing_skus.add(hit['_source']['sku'])
    except: pass

    # Paginated Fetch
    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}/products.json?status=active&limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    
    actions = []
    active_skus = set()

    while url:
        response = requests.get(url, headers=headers)
        if response.status_code != 200: break
        
        products = response.json().get('products', [])
        for product in products:
            category = product.get('product_type') or "General"
            # ✅ Fix: Handle potential NoneType for body_html
            raw_body = product.get('body_html') or ""
            clean_description = clean_html(raw_body[:500])

            for variant in product.get('variants', []):
                sku = variant.get('sku')
                if not sku: continue
                
                active_skus.add(sku)
                actions.append({
                    "_index": PRODUCT_INDEX,
                    "_id": sku,
                    "_source": {
                        "sku": sku,
                        "name": product['title'],
                        "category": category,
                        "price": float(variant['price']),
                        "qty": int(variant['inventory_quantity'] or 0),
                        "in_stock": int(variant['inventory_quantity'] or 0) > 0,
                        "description": clean_description,
                        "updated_at": product['updated_at']
                    }
                })
        # Check for next page
        link = response.headers.get('Link')
        url = re.findall(r'<(.*?)>; rel="next"', link)[0] if link and 'rel="next"' in link else None

    # Cleanup Deletions
    for sku in (existing_skus - active_skus):
        actions.append({"_op_type": "delete", "_index": PRODUCT_INDEX, "_id": sku})

    # Updated line in master_sync.py
    if actions:
        print(f"\n--- 💾 Executing {len(actions)} total actions ---")
        # ✅ Add stats_only=False and raise_on_error=False
        success, errors = helpers.bulk(
            os_client, 
            actions, 
            stats_only=False, 
            raise_on_error=False
        )
        
        print(f"✅ DEBUG: Sync complete. {success} operations successful.")
        
        # Optional: Filter out the 404s from your debug logs
        real_errors = [e for e in errors if list(e.values())[0].get('status') != 404]
        if real_errors:
            print(f"❌ DEBUG: Actual failures: {json.dumps(real_errors, indent=2)}")

# --- 2. SITE FACTS SYNC ---
def sync_site_facts():
    print(f"--- 🌐 Starting Site Facts Sync ---")
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    base = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}"
    actions = []

    # Pages
    pages = requests.get(f"{base}/pages.json", headers=headers).json().get('pages', [])
    for p in pages:
        actions.append({"_index": FACTS_INDEX, "_id": f"page_{p['id']}", "_source": {"type": "Page", "title": p['title'], "content": clean_html(p['body_html']), "confidence": 100, "source": "Shopify"}})

    # Policies
    policies = requests.get(f"{base}/policies.json", headers=headers).json().get('policies', [])
    for pol in policies:
        actions.append({"_index": FACTS_INDEX, "_id": f"policy_{pol['title'].lower()}", "_source": {"type": "Policy", "title": pol['title'], "content": clean_html(pol.get('body') or pol.get('body_html')), "confidence": 100, "source": "Shopify"}})

    helpers.bulk(os_client, actions)
    print(f"✅ Site Facts Updated.")

if __name__ == "__main__":
    sync_all_products()
    sync_site_facts()