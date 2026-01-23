from search.opensearch_client import search_opensearch

MAX_DOCS = 5
MAX_TEXT_CHARS = 900


def _trim(text: str) -> str:
    return text[:MAX_TEXT_CHARS]


def retrieve_context(query: str, intent: str) -> str:
    q = query.lower()

    site_fact_triggers = [
        "frono", "about", "sell", "product", "products",
        "category", "categories", "range",
        "christmas", "seasonal", "heating", "garden"
    ]

    if intent in {"ABOUT_BRAND", "GENERAL", "PRODUCT_INFO"} or any(k in q for k in site_fact_triggers):
        results = search_opensearch(
            index="frono_site_facts",
            query={
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "content^2", "type"]
                }
            },
            limit=5
        )

        if not results:
            return ""

        # Already sorted by score + confidence
        return "\n".join(
            f"- {r['title']}: {r['content'][:900]}"
            for r in results
        )

    return ""
