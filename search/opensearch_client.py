from opensearchpy import OpenSearch
from config import OPENSEARCH_HOST, OPENSEARCH_PORT

client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
    use_ssl=False,
    verify_certs=False,
    http_compress=True
)

def ping() -> bool:
    try:
        return client.ping()
    except Exception:
        return False

def search_opensearch(index: str, query: dict, limit: int = 3):
    response = client.search(
        index=index,
        body={
            "size": limit,
            "query": query
        }
    )
    return [hit["_source"] for hit in response["hits"]["hits"]]
