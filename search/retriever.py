from search.opensearch_client import search_opensearch

MAX_DOCS = 5
MAX_TEXT_CHARS = 900


def _trim(text: str) -> str:
    return text[:MAX_TEXT_CHARS]


def retrieve_context(query: str, intent: str) -> str:
    q = query.lower()

    # 🔒 FORCE SITE FACTS FOR BRAND / CATEGORIES / PRODUCT RANGE
    site_fact_triggers = [
        "frono",
        "about",
        "sell",
        "product",
        "products",
        "category",
        "categories",
        "range",
        "christmas",
        "seasonal",
        "heating",
        "garden",
        "decor",
        "decoration",
        "tree",
        "lights"
    ]

    if intent in {"ABOUT_BRAND", "GENERAL", "PRODUCT_INFO"} or any(k in q for k in site_fact_triggers):
        results = search_opensearch(
            index="frono_site_facts",
            query={
                "multi_match": {
                    "query": query,
                    "fields": [
                        "title^3",
                        "content^2",
                        "type"
                    ]
                }
            },
            limit=MAX_DOCS
        )

        if not results:
            return ""

        return "\n".join(
            f"- {r['title']}: {_trim(r['content'])}"
            for r in results
        )

    # 🛒 SPECIFIC PRODUCT SEARCH (SKU-level, optional)
    results = search_opensearch(
        index="frono_products",
        query={
            "multi_match": {
                "query": query,
                "fields": ["title^3", "description"]
            }
        },
        limit=MAX_DOCS
    )

    if not results:
        return ""

    return "\n".join(
        _trim(r.get("description", ""))
        for r in results
        if r.get("description")
    )
