from search.opensearch_client import ping

def check_health():
    return {
        "status": "ok" if ping() else "degraded"
    }
