import re
from llm.llama_client import LLaMAClient

llama = LLaMAClient()

# --- PATTERN DEFINITIONS ---

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

# NEW: Patterns for short follow-up phrases that should trigger RAG, not a greeting
CONTINUATION_PATTERNS = [
    r"\b(more|else|other|next|okay|ok|yes|yeah)\b",
    r"\b(continue|go on|anything else)\b"
]


def match_patterns(text: str, patterns: list) -> bool:
    """Helper to check if any regex pattern matches the text."""
    return any(re.search(p, text) for p in patterns)


def detect_intent(text: str) -> str:
    """
    Classifies the user's message into an intent category.
    """
    q = text.lower().strip()

    # 1. 🔒 HARD BRAND OVERRIDE (TOP PRIORITY)
    # Catches direct questions about identity
    if (
        q in {"about", "about frono", "tell me about frono", "what is frono", "who are you"}
        or ("frono" in q and any(w in q for w in ["about", "what", "who"]))
    ):
        return "ABOUT_BRAND"

    # 2. 🛒 BUYING INTENT
    if match_patterns(q, BUYING_PATTERNS):
        return "BUYING"

    # 3. 📦 PRODUCT INFORMATION
    if match_patterns(q, PRODUCT_PATTERNS):
        return "PRODUCT_INFO"

    # 4. 🛠 SUPPORT / POLICY
    if match_patterns(q, SUPPORT_PATTERNS):
        return "SUPPORT"

    # 5. 🔄 CONTINUATION CHECK (The Fix)
    # If the user says "okay", "any more", "what else", treat it as 
    # a request for more info (PRODUCT_INFO) instead of a greeting.
    if match_patterns(q, CONTINUATION_PATTERNS):
        return "PRODUCT_INFO"

    # 6. 👀 CASUAL / BROWSING (Short input fallback)
    # Only returns BROWSING if it wasn't caught by the continuation check above
    if len(q.split()) <= 3:
        return "BROWSING"

    # 7. 🤖 LLM FALLBACK (For complex/ambiguous queries)
    return llm_intent_fallback(text)


def llm_intent_fallback(message: str) -> str:
    """
    Uses LLaMA to classify ambiguous messages that failed regex matching.
    """
    prompt = (
        "Classify the user message into ONE category:\n"
        "ABOUT_BRAND, BUYING, PRODUCT_INFO, SUPPORT, BROWSING.\n"
        "Reply with only the category name.\n\n"
        f"Message: {message}"
    )

    # Generate and clean up response
    result = llama.generate(prompt).upper()

    # robust check to find the keyword in the response
    for intent in ["ABOUT_BRAND", "BUYING", "PRODUCT_INFO", "SUPPORT", "BROWSING"]:
        if intent in result:
            return intent

    # Default fallback if LLM gets confused
    return "BROWSING"