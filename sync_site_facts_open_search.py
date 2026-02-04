import requests
import json
from opensearchpy import OpenSearch, helpers
from config import (
    SHOPIFY_ACCESS_TOKEN, 
    SHOPIFY_STORE_NAME, 
    API_VERSION, 
    OPENSEARCH_HOST
)

# Initialize OpenSearch Client
os_client = OpenSearch(
    hosts=[{'host': OPENSEARCH_HOST, 'port': 9200}],
    http_compress=True
)

FACTS_INDEX = "frono_site_facts"

def clean_html(raw_html):
    """Simple helper to strip HTML tags for cleaner search content."""
    import re
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

def sync_site_facts():
    print(f"\n--- 🌐 Starting Site Facts Sync for {SHOPIFY_STORE_NAME} ---")
    
    # Endpoints for Pages and Policies
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    base_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{API_VERSION}"
    
    actions = []

    # 1. Fetch Custom Pages (About Us, Contact, etc.)
    try:
        pages_res = requests.get(f"{base_url}/pages.json", headers=headers)
        pages = pages_res.json().get('pages', [])
        print(f"📄 DEBUG: Fetched {len(pages)} pages from Shopify.")
        
        for page in pages:
            actions.append({
                "_index": FACTS_INDEX,
                "_id": f"page_{page['id']}",
                "_source": {
                    "type": "Page",
                    "title": page['title'],
                    "content": clean_html(page['body_html']),
                    "confidence": 100,
                    "source": "Shopify Pages"
                }
            })
            print(f"📝 DEBUG: Prepared Page - {page['title']}")
    except Exception as e:
        print(f"❌ DEBUG: Failed to fetch Pages: {e}")

    # 2. Fetch Store Policies (Refund, Shipping, Privacy)
    # Updated sync_site_facts logic for policies
    try:
        policies_res = requests.get(f"{base_url}/policies.json", headers=headers)
        policies = policies_res.json().get('policies', [])
        print(f"⚖️ DEBUG: Fetched {len(policies)} policies from Shopify.")
        
        for policy in policies:
            # ✅ FIX: Policies use 'body', Pages use 'body_html'
            content = policy.get('body') or policy.get('body_html')
            
            actions.append({
                "_index": FACTS_INDEX,
                "_id": f"policy_{policy.get('handle') or policy['title'].lower().replace(' ', '_')}",
                "_source": {
                    "type": "Policy",
                    "title": policy['title'],
                    "content": clean_html(content),
                    "confidence": 100,
                    "source": "Shopify Policies"
                }
            })
            print(f"📝 DEBUG: Prepared Policy - {policy['title']}")
    except Exception as e:
        print(f"❌ DEBUG: Failed to fetch Policies: {e}")

    # 3. Commit to OpenSearch
    if actions:
        success, _ = helpers.bulk(os_client, actions)
        print(f"✅ DEBUG: Successfully updated {success} site facts in index.")
    else:
        print("⚠️ DEBUG: No site facts found to sync.")

if __name__ == "__main__":
    # You can call both your product sync and facts sync here
    # sync_active_inventory() 
    sync_site_facts()