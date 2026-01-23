import re
from llm.llama_client import LLaMAClient

llama = LLaMAClient()

BUYING_PATTERNS = [
    r"\b(buy|order|purchase|checkout|price|cost)\b",
    r"\b(add to cart|place order)\b"
]

PRODUCT_PATTERNS = [
    r"\b(feature|spec|detail|difference|compare)\b",
    r"\b(size|material|color)\b"
]

SUPPORT_PATTERNS = [
    r"\b(return|refund|shipping|delivery|warranty)\b",
    r"\b(cancel|exchange)\b"
]


def match_patterns(text: str, patterns: list) -> bool:
    return any(re.search(p, text) for p in patterns)


def detect_intent(text: str) -> str:
    q = text.lower().strip()

    # 🔒 HARD BRAND OVERRIDE (TOP PRIORITY)
    if (
        q in {"about", "about frono", "tell me about frono", "what is frono", "who are you"}
        or ("frono" in q and any(w in q for w in ["about", "what", "who"]))
    ):
        return "ABOUT_BRAND"

    # 🛒 BUYING INTENT
    if match_patterns(q, BUYING_PATTERNS):
        return "BUYING"

    # 📦 PRODUCT INFORMATION
    if match_patterns(q, PRODUCT_PATTERNS):
        return "PRODUCT_INFO"

    # 🛠 SUPPORT / POLICY
    if match_patterns(q, SUPPORT_PATTERNS):
        return "SUPPORT"

    # 👀 CASUAL / BROWSING
    if len(q.split()) <= 3:
        return "BROWSING"

    # 🤖 LLM FALLBACK (RARE)
    return llm_intent_fallback(text)


def llm_intent_fallback(message: str) -> str:
    prompt = (
        "Classify the user message into ONE category:\n"
        "ABOUT_BRAND, BUYING, PRODUCT_INFO, SUPPORT, BROWSING.\n"
        "Reply with only the category name.\n\n"
        f"Message: {message}"
    )

    result = llama.generate(prompt).upper()

    for intent in ["ABOUT_BRAND", "BUYING", "PRODUCT_INFO", "SUPPORT", "BROWSING"]:
        if intent in result:
            return intent

    return "BROWSING"
