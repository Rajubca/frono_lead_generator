from datetime import date
from search.opensearch_client import client

INDEX = "frono_products"


class StockService:

    @staticmethod
    def get_by_sku(sku: str):
        query = {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"sku.keyword": sku}},
                        {"match": {"sku": sku}}
                    ]
                }
            }
        }

        # ✅ FIX: Add seq_no_primary_term=True to get the metadata
        result = client.search(
            index=INDEX,
            body=query,
            seq_no_primary_term=True
        )

        hits = result["hits"]["hits"]

        if not hits:
            return None

        return hits[0] # Returns full metadata + source

    @staticmethod
    def reserve_and_commit(sku: str, qty: int):
        """
        Atomic stock reduction with optimistic locking
        """

        doc = StockService.get_by_sku(sku)

        if not doc:
            raise Exception("Product not found")

        doc_id = doc["_id"]
        src = doc["_source"]

        seq_no = doc["_seq_no"]
        primary_term = doc["_primary_term"]

        if src["qty"] < qty:
            raise Exception("Insufficient stock")

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
                    "q": qty,
                    "today": today
                }
            }
        }

        result = client.update(
            index=INDEX,
            id=doc_id,
            if_seq_no=seq_no,
            if_primary_term=primary_term,
            body=body
        )

        return result
