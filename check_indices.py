
from opensearchpy import OpenSearch
from config import OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_USE_SSL

def get_opensearch_connection():
    try:
        # Use keyword arguments to ensure compatibility with modern opensearch-py
        client = OpenSearch(
            hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
            use_ssl=OPENSEARCH_USE_SSL,
            verify_certs=False,
            ssl_show_warn=False
        )
        return client
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def list_all_indices():
    client = get_opensearch_connection()
    
    if client and client.ping():
        print("✅ Connected to OpenSearch successfully.\n")
        
        try:
            # FIX: Use keyword argument 'index' or the cat API for listing
            indices = client.cat.indices(format="json")
            
            print(f"{'Index Name':<30} | {'Docs Count':<10} | {'Status'}")
            print("-" * 55)
            
            for index in indices:
                name = index['index']
                # Skip internal system indices starting with '.'
                if not name.startswith('.'):
                    count = index.get('docs.count', '0')
                    status = index.get('status', 'open')
                    print(f"{name:<30} | {count:<10} | {status}")
                    
        except Exception as e:
            print(f"❌ Error fetching indices: {e}")
    else:
        print("❌ Could not reach OpenSearch. Check if the service is running.")


# verify_id_mismatch.py
from opensearchpy import OpenSearch
from config import OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_USE_SSL

client = OpenSearch(
    hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
    use_ssl=OPENSEARCH_USE_SSL,
    verify_certs=False
)

def check_sku_vs_id(sku_to_find="HTR-001"):
    # Search for the document by the SKU field
    res = client.search(
        index="frono_products",
        body={"query": {"term": {"sku.keyword": sku_to_find}}}
    )
    
    if res['hits']['total']['value'] > 0:
        doc = res['hits']['hits'][0]
        actual_id = doc['_id']
        sku_value = doc['_source']['sku']
        
        print(f"--- DATA CHECK ---")
        print(f"Field 'sku' in data: {sku_value}")
        print(f"Internal Document '_id': {actual_id}")
        
        if actual_id == sku_value:
            print("\n✅ SUCCESS: Your ID matches your SKU. client.update() should work.")
        else:
            print("\n❌ MISMATCH: Your ID is a random string.")
            print(f"This is why client.update(id='{sku_value}') fails with a 404.")
            print("You MUST use update_by_query to update this document.")
    else:
        print(f"SKU {sku_to_find} not found. Check your index data.")
# check_raw_data.py
from opensearchpy import OpenSearch
from config import OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_USE_SSL

client = OpenSearch(
    hosts=[{'host': OPENSEARCH_HOST, 'port': OPENSEARCH_PORT}],
    use_ssl=OPENSEARCH_USE_SSL,
    verify_certs=False
)

def see_everything():
    # Fetch all 4 documents from the product index
    res = client.search(index="frono_products", body={"query": {"match_all": {}}})
    hits = res['hits']['hits']
    
    print(f"--- FOUND {len(hits)} PRODUCTS ---")
    for h in hits:
        source = h['_source']
        print(f"ID: {h['_id']} | SKU: '{source.get('sku')}' | Name: {source.get('name')}")

if __name__ == "__main__":
    print("\n--- RAW DATA CHECK ---\n")
    see_everything()
    print("\n--- ID vs SKU CHECK ---\n")
    check_sku_vs_id()
    print("\n--- LIST OF INDICES ---\n")
    list_all_indices()