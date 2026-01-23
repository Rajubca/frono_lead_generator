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
    text = text.lower()
    return any(re.search(p, text) for p in patterns)


def detect_intent(text: str) -> str:
    q = text.lower().strip()

    # BRAND / ABOUT FRONO (HIGH PRIORITY)
    if q in ["about", "about frono", "tell me about frono", "what is frono", "who are you"]:
        return "ABOUT_BRAND"

    if "frono" in q and any(word in q for word in ["about", "what", "who"]):
        return "ABOUT_BRAND"

 
    # Fallback to LLM (only if needed)
    # return llm_intent_fallback(message)


def llm_intent_fallback(message: str) -> str:
    prompt = (
        "Classify the user message into one category:\n"
        "BUYING, PRODUCT_INFO, SUPPORT, BROWSING, UNKNOWN.\n"
        "Reply with only the category name.\n\n"
        f"Message: {message}"
    )

    result = llama.generate(prompt).upper()

    for intent in ["BUYING", "PRODUCT_INFO", "SUPPORT", "BROWSING"]:
        if intent in result:
            return intent

    return "UNKNOWN"
