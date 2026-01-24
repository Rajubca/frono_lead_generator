import re
from llm.llama_client import LLaMAClient

llama = LLaMAClient()

# --- 1. ACTION PATTERNS (Verbs/Intents) ---
BUYING_PATTERNS = [
    r"\b(buy|order|purchase|checkout|price|cost|pay)\b",
    r"\b(add to cart|place order|how much)\b"
]

SUPPORT_PATTERNS = [
    r"\b(return|refund|shipping|delivery|warranty|track)\b",
    r"\b(cancel|exchange|broken|damaged|late|arrive)\b"
]

# --- 2. PRODUCT PATTERNS (Attributes & Nouns) ---
# Attributes
PRODUCT_ATTRIBUTES = [
    r"\b(feature|spec|detail|difference|compare|desc)\b",
    r"\b(size|material|color|dimension|weight|height|width)\b"
]

# Nouns (The actual items Frono sells)
PRODUCT_NOUNS = [
    r"\b(tree|garland|wreath|bauble|light|decoration|ornament)\b", # Christmas
    r"\b(heater|radiator|quartz|oil|fan|warm)\b",                   # Heating
    r"\b(tub|spa|pool|filter|chemical|pump|chlorine)\b",             # Hot Tub
    r"\b(furniture|sofa|rattan|table|chair|dining|gazebos|parasol)\b", # Garden
    r"\b(mat|cover|bulb|bow|suit|costume)\b",                        # Misc
    
    # <--- ADD THIS LINE HERE:
    r"\b(category|categories|catalog|catalogue|range|list|products|item|collection)\b" 
]

# --- 3. CONVERSATION FLOW ---
CONTINUATION_PATTERNS = [
    r"\b(more|else|other|next|okay|ok|yes|yeah|sure)\b",
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

    # 1. 🔒 HARD BRAND OVERRIDE (Identity)
    if (
        q in {"about", "about frono", "tell me about frono", "what is frono", "who are you"}
        or ("frono" in q and any(w in q for w in ["about", "what", "who"]))
    ):
        return "ABOUT_BRAND"

    # 2. 🛒 BUYING INTENT
    if match_patterns(q, BUYING_PATTERNS):
        return "BUYING"

    # 3. 🛠 SUPPORT / POLICY
    if match_patterns(q, SUPPORT_PATTERNS):
        return "SUPPORT"

    # 4. 📦 PRODUCT INFORMATION (Nouns & Attributes)
    # Check if the user named a product (e.g., "oil heater") OR an attribute
    if match_patterns(q, PRODUCT_NOUNS) or match_patterns(q, PRODUCT_ATTRIBUTES):
        return "PRODUCT_INFO"

    # 5. 🔄 CONTINUATION CHECK (Fixes "okay what else")
    if match_patterns(q, CONTINUATION_PATTERNS):
        return "PRODUCT_INFO"

    # 6. 👀 CASUAL / BROWSING (Short input fallback)
    # Only returns BROWSING if no product keyword was found above
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

    try:
        # Generate and clean up response
        result = llama.generate(prompt).upper()

        for intent in ["ABOUT_BRAND", "BUYING", "PRODUCT_INFO", "SUPPORT", "BROWSING"]:
            if intent in result:
                return intent
                
    except Exception:
        pass

    # Default fallback if LLM fails or gets confused
    return "BROWSING"