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
    - Handles Category Discovery specifically
    - Uses frono_products for inventory queries
    - Uses frono_site_facts for brand/policy queries
    """
    q_lower = query.lower()

    # --- New: Category Discovery Logic ---
    # If the user is asking "what categories" or "show products"
    category_keywords = ["category", "categories", "catalog", "range", "list", "collection", "collections"]
    if any(k in q_lower for k in category_keywords) and len(q_lower.split()) < 6:
        return (
            "Frono.uk offers a wide range of products including:\n"
            "- Christmas Shop (Artificial Trees, Tree Stands, LED Lights, and Decorations)\n"
            "- Seasonal Heating (Oil Filled Radiators, Quartz, Fan, and Halogen Heaters)\n"
            "- Lighting (LED Parcel, Rope, Curtain, and Twig Tree Lights)\n"
            "- Garden & Outdoor Furniture (Sofa sets, Gazebos)\n"
            "- Hot Tubs & Spas\n\n"
            "Would you like to explore a specific category?"
        )

    # ----------------------------------
    # 1. Detect Product / Buying Intents
    # ----------------------------------
    product_intents = ["BUYING", "PRODUCT_INFO", "AFFIRMATION"]

    if intent in product_intents:
        product_results = search_opensearch(
            index="frono_products",
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["name^3", "description^2", "category"],
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

        if product_results:
            items = []
            for r in product_results:
                items.append(
                    f"- {r['name']} (£{r.get('price','N/A')} | Stock: {r.get('qty',0)})"
                )
            product_text = "\n".join(items)
            return (
                "Available products in stock:\n"
                f"{product_text}\n\n"
                "You may ask for details, comparison, or ordering."
            )

        # -------------------------------
        # Refined Fallback for No Stock
        # -------------------------------
        return (
            "I couldn't find a specific product match for that in our current inventory. "
            "We generally carry Heaters, Lights, and Garden Furniture. "
            "Would you like me to check our full Seasonal Heating or Lighting range instead?"
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

