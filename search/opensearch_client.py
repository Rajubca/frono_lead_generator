from opensearchpy import OpenSearch

from config import OPENSEARCH_HOST

client = OpenSearch(OPENSEARCH_HOST)

def ping() -> bool:
    """
    Health check for OpenSearch
    """
    try:
        return client.ping()
    except Exception:
        return False

def search_opensearch(index: str, query: dict, limit: int = 5):
    """
    Index-aware, fault-tolerant OpenSearch query.
    """

    body = {
        "size": limit,
        "query": query,
        "_source": True   # Can be restricted later
    }

    # Knowledge index: confidence sorting
    if index == "frono_site_facts":
        body["sort"] = [
            {"_score": {"order": "desc"}},
            {"confidence": {"order": "desc", "missing": "_last"}}
        ]

    # Product index: relevance only
    else:
        body["sort"] = [
            {"_score": {"order": "desc"}}
        ]

    try:
        res = client.search(
            index=index,
            body=body,
            request_timeout=10
        )

        hits = res.get("hits", {}).get("hits", [])

        return [h["_source"] for h in hits]

    except Exception as e:
        print("OpenSearch search error:", e)
        return []
