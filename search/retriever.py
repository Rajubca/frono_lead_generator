from search.opensearch_client import client, search_opensearch
import time
from search.opensearch_client import client, search_opensearch

# ---------------- COLLECTION GROUPS ----------------
from admin.config_manager import ConfigManager
MAX_PRODUCTS_TO_SHOW = ConfigManager.get_setting("max_products_to_show", 3)

COLLECTION_GROUPS = {
    "Pest Control": [
        "Pest Control",
        "Garden Care",
        "Home Care",
        "Home & Garden",
        "Outdoor Products",
        "Cleaning",
        "Household",
        "AVADA - Best Sellers"
    ],

    "Heaters": [
        "Heaters",
        "Winter Essentials",
        "Home Heating",
        "AVADA - Best Sellers"
    ],
    "Christmas Products": [
        "Christmas",
        "Christmas Lighting",
        "Christmas Costume",
        "Sacks & Stockings",
        "Christmas Nutcrackers"
    ]
}

# ---------------- COLLECTION CACHE ----------------
_COLLECTION_CACHE = {
    "data": None,
    "timestamp": 0
}

_COLLECTION_CACHE_TTL = 300  # seconds (5 minutes)

def normalize_query(text: str) -> str:
    text = text.lower().strip()
    if text.endswith("s"):
        text = text[:-1]
    return text

import json

def resolve_group_from_query(query: str) -> str | None:
    q = query.lower()
    # Fetch the dynamic dictionary from Admin Config
    raw_groups = ConfigManager.get_setting("collection_groups_json", "{}")
    groups_dict = json.loads(raw_groups) if raw_groups else {}

    for group, keywords in groups_dict.items():
        for kw in keywords:
            if kw in q:
                return group
    return None

def get_collections_for_group(group: str) -> list[str]:
    return COLLECTION_GROUPS.get(group, [])


def resolve_collection_group(query: str) -> str | None:
    q = query.lower()

    for group in COLLECTION_GROUPS:
        if group.lower() in q:
            return group

    return None



import time

def get_all_collections():
    now = time.time()

    if (
            _COLLECTION_CACHE["data"]
            and now - _COLLECTION_CACHE["timestamp"] < _COLLECTION_CACHE_TTL
        ):
        return _COLLECTION_CACHE["data"]

    res = client.search(
        index="frono_products",
        body={
            "size": 0,
            "aggs": {
                "collections": {
                    "terms": {
                        "field": "collection",
                        "size": 100
                    }
                }
            }
        }
    )

    buckets = (
        res.get("aggregations", {})
           .get("collections", {})
           .get("buckets", [])
    )

    collections = [b["key"] for b in buckets]

    _COLLECTION_CACHE["data"] = collections
    _COLLECTION_CACHE["timestamp"] = now

    return collections


def get_product_by_name(identifier: str):
    results = search_opensearch(
        index="frono_products",
        query={
            "bool": {
                "should": [
                    {"term": {"sku.keyword": identifier}},
                    {"match": {"name": {"query": identifier, "operator": "and"}}}
                ]
            }
        },
        limit=1
    )
    return results[0] if results else None


def retrieve_context(query: str, intent: str, session: dict | None) -> str | None:
    """
    Truth-gated retriever.
    Returns ONLY verified information or None.
    """

    # 0️⃣ Brand / About
    if intent == "ABOUT_BRAND":
        results = search_opensearch(
            index="frono_site_facts",
            query={"term": {"type": "about"}},
            limit=1
        )
        if results:
            return results[0]["content"]
        # fallback if about page not indexed
        return (
            "Hi! Welcome to Frono.uk 👋\n"
            "We offer Christmas products, heaters, outdoor items, and more.\n"
            "How can I help you today?"
        )

    # 1️⃣ Collection / Browse queries
    # 1️⃣ Dynamic collection-based search
    collections = get_all_collections()
    # 1️⃣ Collection Group Based Search
    normalized_query = normalize_query(query)
    group = resolve_group_from_query(normalized_query)


    if group:
        collections = get_collections_for_group(group)
        results = []

        if collections:
            results = search_opensearch(
                index="frono_products",
                query={
                    "bool": {
                        "filter": [
                            {"terms": {"collection": collections}},
                            {"range": {"qty": {"gt": 0}}}
                        ]
                    }
                },
                limit=MAX_PRODUCTS_TO_SHOW + 1
            )

        if results:
            visible = results[:MAX_PRODUCTS_TO_SHOW]

            has_more = len(results) > MAX_PRODUCTS_TO_SHOW

            if session is not None:
                session["menu"] = {str(i+1): r['name'] for i, r in enumerate(visible)}
            
            # --- FIX: Proper numbered formatting + No Stock unless requested ---
            items = []
            for i, r in enumerate(visible):
                price = f"£{float(r['price']):,.2f}"
                # Only show stock if low (urgency) or explicitly buying
                stock_info = ""
                if intent == "BUYING" or r.get("qty", 0) < 5:
                    stock_info = f" (Only {r.get('qty', 0)} left!)"

                items.append(f"{i+1}. **{r['name']}** — {price}{stock_info}")

            response = (
                f"Here are some {group} products currently available:\n"
                + "\n".join(items) # Use single newline for compact list
            )

            if has_more:
                response += (
                    "\n\n…and more products are available."
                    "\nType **show more** to see additional options."
                )

            return response

        # ✅ NOW this executes correctly
        related_groups = [
            g for g in COLLECTION_GROUPS.keys()
            if g != group
        ][:2]

        suggestions = "\n".join(f"• {g}" for g in related_groups)

        return (
            f"We don’t currently have available products under **{group}**.\n\n"
            f"You may want to explore:\n"
            f"{suggestions}"
        )


    # 2️⃣ Product search
    product_results = search_opensearch(
        index="frono_products",
        query={
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["name^3", "description^2", "collection^2"],
                            "fuzziness": "AUTO"
                        }
                    }
                ],
                "filter": [{"range": {"qty": {"gt": 0}}}]
            }
        },
        limit=5
    )

    if session is not None:
            session["menu"] = {str(i+1): r['name'] for i, r in enumerate(product_results[:MAX_PRODUCTS_TO_SHOW])}
            
            items = []
            for i, r in enumerate(product_results[:MAX_PRODUCTS_TO_SHOW]):
                price = f"£{float(r['price']):,.2f}"
                stock_info = ""
                # Only show stock if low or buying intent
                if intent == "BUYING" or r.get("qty", 0) < 5:
                    stock_info = f" (Only {r.get('qty', 0)} left!)"

                items.append(f"{i+1}. **{r['name']}** — {price}{stock_info}")

            # --- FIX: Force single newlines in context for cleaner list ---
            return "Here are some products that match your request:\n" + "\n".join(items)

    # 3️⃣ Policy / Knowledge
    policy_results = search_opensearch(
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

    if policy_results:
        return (
            "Here’s the verified information regarding your question:\n"
            + "\n".join(
                f"- {r['title']}: {r['content']}"
                for r in policy_results
            )
        )

    return None
