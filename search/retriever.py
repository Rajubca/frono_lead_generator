from search.opensearch_client import search_opensearch
from config import STORE_SUMMARY  # Import the fallback

MAX_TEXT_CHARS = 1500

def retrieve_context(query: str, intent: str) -> str:
    q = query.lower()

    # triggers that indicate we should look for specific facts
    site_fact_triggers = [
        "frono", "about", "sell", "product", "products",
        "category", "categories", "range",
        "christmas", "seasonal", "heating", "garden", "hot tub"
    ]

    # 1. Try Specific Search
    results = search_opensearch(
        index="frono_site_facts",
        query={
            "multi_match": {
                "query": query,
                "fields": ["title^3", "content^2", "type"],
                "fuzziness": "AUTO"  # Helps with typos
            }
        },
        limit=3
    )

    # 2. Format Results
    if results:
        specific_context = "\n".join(
            f"- {r['title']}: {r['content']}" for r in results
        )
        # Combine specific hits with general store knowledge
        return f"{STORE_SUMMARY}\n\nSpecific Details found:\n{specific_context}"

    # 3. If Search Empty -> Return General Store Summary (Fixes "Verified info" error)
    return STORE_SUMMARY