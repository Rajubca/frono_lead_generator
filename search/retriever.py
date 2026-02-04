from search.opensearch_client import search_opensearch
from config import STORE_SUMMARY

MAX_TEXT_CHARS = 1500

def get_product_by_name(identifier: str):
    results = search_opensearch(
        index="frono_products",
        query={
            "bool": {
                "should": [
                    {
                        "term": {
                            "sku.keyword": identifier
                        }
                    },
                    {
                        "match": {
                            "name": {
                                "query": identifier,
                                "operator": "and"
                            }
                        }
                    }
                ]
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
                raw_price = r.get('price', 0)
                try:
                    # Force the format to £4,999.00 or £49.99 specifically
                    formatted_price = f"£{float(raw_price):,.2f}" 
                except (ValueError, TypeError):
                    formatted_price = f"£{raw_price}"

                items.append(
                    f"- {r['name']} ({formatted_price} | Stock: {r.get('qty', 0)})"
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
            "We don't currently carry that specific item, but we have a wide range of "
            "enabled products in our Shopify store that might interest you:\n"
            "- Seasonal Heating (Oil Filled Radiators, Fan Heaters)\n"
            "- Christmas Shop (Trees, LED Lights)\n"
            "- Garden Furniture & Hot Tubs\n\n"
            "Would you like to explore one of these collections instead?"
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

