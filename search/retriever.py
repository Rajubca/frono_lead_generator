from search.opensearch_client import search_opensearch

MAX_DOCS = 3
MAX_TEXT_CHARS = 800


def _trim(text: str) -> str:
    return text[:MAX_TEXT_CHARS]

def retrieve_context(query: str, intent: str) -> str:
    q = query.lower()

    # 🔒 HARD BRAND OVERRIDE
    if "frono" in q or "about" in q:
        intent = "ABOUT"

def retrieve_context(query: str, intent: str) -> str:
    """
    Returns VERIFIED context only.
    Returns empty string if nothing reliable is found.
    """

    # ---------------- BRAND / ABOUT ----------------
    if intent in {"ABOUT", "BRAND", "GENERAL"}:
        results = search_opensearch(
            index="frono_site_facts",
            query={
                "bool": {
                    "should": [
                        {"term": {"type": "about"}},
                        {"term": {"type": "products"}},
                        {"term": {"type": "policy"}},
                        {"term": {"type": "legitimacy"}},
                        {"term": {"type": "brand"}},
                        {"term": {"type": "disambiguation"}}
                    ],
                    "minimum_should_match": 1
                }
            },
            limit=3
        )

        if not results:
            return ""

        return "\n".join(
            f"- {r['title']}: {_trim(r['content'])}"
            for r in results
        )

    # ---------------- PRODUCT / BUYING ----------------
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
