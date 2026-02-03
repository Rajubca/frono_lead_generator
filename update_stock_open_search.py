from opensearchpy import OpenSearch
from datetime import date

# ----------------------------------------
# CONFIG
# ----------------------------------------

INDEX_NAME = "frono_products"

OPENSEARCH_HOST = "localhost"     # change if needed
OPENSEARCH_PORT = 9200            # change if needed
USERNAME = "admin"               # if auth enabled
PASSWORD = "admin"               # if auth enabled


# ----------------------------------------
# CONNECT
# ----------------------------------------

client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
    http_auth=(USERNAME, PASSWORD),
    use_ssl=False,
    verify_certs=False
)


# ----------------------------------------
# STEP 1: FIND DOCUMENT BY SKU
# ----------------------------------------

def get_doc_by_sku(sku: str):

    query = {
        "query": {
            "bool": {
                "should": [
                    { "term": { "sku.keyword": sku } },
                    { "match": { "sku": sku } }
                ]
            }
        }
    }

    result = client.search(
        index=INDEX_NAME,
        body=query
    )

    hits = result["hits"]["hits"]

    if not hits:
        print(f"❌ No product found for SKU: {sku}")
        return None

    return hits[0]


# ----------------------------------------
# STEP 2: UPDATE STOCK USING _id
# ----------------------------------------

def update_stock_by_id(doc_id: str, qty_to_reduce: int):

    today = date.today().isoformat()

    body = {
        "script": {
            "source": """
                if (ctx._source.qty >= params.q) {
                    ctx._source.qty -= params.q;
                    ctx._source.in_stock = ctx._source.qty > 0;
                    ctx._source.updated_at = params.today;
                }
            """,
            "params": {
                "q": qty_to_reduce,
                "today": today
            }
        }
    }

    result = client.update(
        index=INDEX_NAME,
        id=doc_id,
        body=body
    )

    return result


# ----------------------------------------
# MAIN FUNCTION
# ----------------------------------------

def update_stock_by_sku(sku: str, qty: int):

    print(f"🔍 Searching for SKU: {sku}")

    doc = get_doc_by_sku(sku)

    if not doc:
        return

    doc_id = doc["_id"]
    source = doc["_source"]

    print("✅ Found product:")
    print("   ID   :", doc_id)
    print("   Name :", source["name"])
    print("   Qty  :", source["qty"])

    if source["qty"] < qty:
        print("❌ Not enough stock")
        return

    print(f"📉 Reducing stock by {qty}...")

    result = update_stock_by_id(doc_id, qty)

    print("✅ Update Result:", result)

    print("🎉 Stock updated successfully!")


# ----------------------------------------
# RUN
# ----------------------------------------

if __name__ == "__main__":

    # CHANGE THESE VALUES
    SKU = "HTR-001"
    QTY_TO_REDUCE = 5

    update_stock_by_sku(SKU, QTY_TO_REDUCE)
