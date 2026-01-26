from search.opensearch_client import search_opensearch
from config import STORE_SUMMARY

MAX_TEXT_CHARS = 1500

def get_product_by_name(name: str):

    results = search_opensearch(
        index="frono_products",
        query={
            "match": {
                "name": name
            }
        },
        limit=1
    )

    return results[0] if results else None


def retrieve_context(query: str, intent: str) -> str:
    """
    Hybrid retriever:
    - Uses frono_products for inventory queries
    - Uses frono_site_facts for brand/policy queries
    """

    # ----------------------------------
    # 1. Detect Product / Buying Intents
    # ----------------------------------
    product_intents = ["BUYING", "PRODUCT_INFO", "AFFIRMATION"]

    if intent in product_intents:

        # -------------------------------
        # Search Inventory
        # -------------------------------
        product_results = search_opensearch(
            index="frono_products",
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name^3",
                                    "description^2",
                                    "category"
                                ],
                                "fuzziness": "AUTO"
                            }
                        }
                    ],
                    "filter": [
                        { "range": { "qty": { "gt": 0 } } }
                    ]
                }
            },
            limit=5
        )

        # -------------------------------
        # Format Products
        # -------------------------------
        if product_results:

            items = []

            for r in product_results:
                items.append(
                    f"- {r['name']} (£{r.get('price','N/A')} | "
                    f"Stock: {r.get('qty',0)})"
                )

            product_text = "\n".join(items)

            return (
                "Available products in stock:\n"
                f"{product_text}\n\n"
                "You may ask for details, comparison, or ordering."
            )

        # -------------------------------
        # No Stock Found
        # -------------------------------
        return (
            "Currently, the requested products appear to be out of stock "
            "or unavailable. You may ask about alternatives or restocking."
        )

    # ----------------------------------
    # 2. Knowledge / Policy Search
    # ----------------------------------

    results = search_opensearch(
        index="frono_site_facts",
        query={
            "multi_match": {
                "query": query,
                "fields": ["title^3", "content^2", "type"],
                "fuzziness": "AUTO"
            }
        },
        limit=3
    )

    # ----------------------------------
    # 3. Format Knowledge Results
    # ----------------------------------
    if results:

        specific_context = "\n".join(
            f"- {r['title']}: {r['content']}"
            for r in results
        )

        return (
            f"{STORE_SUMMARY}\n\n"
            "Verified information:\n"
            f"{specific_context}"
        )

    # ----------------------------------
    # 4. Fallback
    # ----------------------------------
    return STORE_SUMMARY

