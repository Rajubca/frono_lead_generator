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
    Returns search results sorted by:
    1. relevance (_score)
    2. confidence (descending)
    """

    res = client.search(
        index=index,
        body={
            "size": limit,
            "query": query,
            "sort": [
                {"_score": {"order": "desc"}},
                {"confidence": {"order": "desc", "missing": "_last"}}
            ]
        }
    )

    hits = res.get("hits", {}).get("hits", [])

    return [h["_source"] for h in hits]
