import re
from llm.groq_client import GroqClient 

llama = GroqClient() 

# --- PATTERNS ---
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

AFFIRMATION_PATTERNS = [
    r"\b(yes|yeah|sure|yep|please|interested|do it|send it|i want)\b"
]

BUYING_PATTERNS = [
    r"\b(buy|order|purchase|checkout|price|cost|pay|add to cart)\b"
]

CLOSING_PATTERNS = [
    r"\b(ok|okay|thanks|bye|goodbye|cya)\b"
]

# --- 1. ACTION PATTERNS ---
BUYING_PATTERNS = [
    r"\b(buy|order|purchase|checkout|price|cost|pay)\b",
    r"\b(add to cart|place order|how much)\b"
]

SUPPORT_PATTERNS = [
    r"\b(return|refund|shipping|delivery|warranty|track)\b",
    r"\b(cancel|exchange|broken|damaged|late|arrive)\b"
]

# --- 2. PRODUCT PATTERNS ---
PRODUCT_ATTRIBUTES = [
    r"\b(feature|spec|detail|difference|compare|desc)\b",
    r"\b(size|material|color|dimension|weight|height|width)\b"
]

PRODUCT_NOUNS = [
    r"\b(tree|garland|wreath|bauble|light|decoration|ornament)\b",
    r"\b(heater|radiator|quartz|oil|fan|warm)\b",
    r"\b(tub|spa|pool|filter|chemical|pump|chlorine)\b",
    r"\b(furniture|sofa|rattan|table|chair|dining|gazebos|parasol)\b",
    r"\b(mat|cover|bulb|bow|suit|costume)\b",
    r"\b(category|categories|catalog|catalogue|range|list|products|item|collection)\b" 
]

# --- 3. CONVERSATIONAL PATTERNS (UPDATED) ---

# NEW: Words that mean "I'm done" or "Understood"
CLOSING_PATTERNS = [
    r"\b(okay|ok|thanks|thank you|thx|great|cool|good|perfect|understood|got it)\b",
    r"\b(bye|goodbye|cya|see ya|good night)\b"
]

# UPDATED: Words that specifically ask for MORE info
CONTINUATION_PATTERNS = [
    r"\b(more|else|other|next|continue|go on|anything else)\b",
    r"\b(what else|show me more)\b"
]

# Generic phone pattern for UK/International formats
PHONE_PATTERN = r"(\+?[0-9]{1,3})?[-. ]?([0-9]{3,4})[-. ]?([0-9]{3,4})[-. ]?([0-9]{3,4})"

def extract_contact_info(text: str) -> dict:
    results = {}
    email = re.search(EMAIL_PATTERN, text)
    phone = re.search(PHONE_PATTERN, text)
    
    if email:
        results["email"] = email.group(0)
    if phone:
        results["phone"] = phone.group(0)
    return results

def match_patterns(text: str, patterns: list) -> bool:
    return any(re.search(p, text) for p in patterns)

def detect_intent(text: str) -> str:
    """
    Determines the user's goal based on their message.
    Priority: Capture Email > Identity > Hot Leads (Yes) > Buying > Support > Product Info > Browsing.
    """
    q = text.lower().strip()

    # ---------------------------------------------------------
    # 1. CRITICAL: LEAD CAPTURE (Highest Priority)
    # ---------------------------------------------------------
    # If the user types an email, they are converting. Catch this first.
    if re.search(EMAIL_PATTERN, text):
        return "LEAD_SUBMISSION"

    # ---------------------------------------------------------
    # 2. BRAND IDENTITY
    # ---------------------------------------------------------
    # Questions like "Who are you?", "About Frono".
    if (q in {"about", "about frono", "tell me about frono", "who are you"} or "frono" in q):
        return "ABOUT_BRAND"

    # ---------------------------------------------------------
    # 3. AFFIRMATION / HOT SIGNAL (The "Hook" Response)
    # ---------------------------------------------------------
    # If we asked "Want a discount?" and they say "Yes", catch it here.
    # Must be BEFORE Browsing check so "Yes" isn't treated as a greeting.
    if match_patterns(q, AFFIRMATION_PATTERNS) and len(q.split()) < 6:
        return "AFFIRMATION"

    # ---------------------------------------------------------
    # 4. HIGH VALUE INTENTS (Buying & Support)
    # ---------------------------------------------------------
    # Clear signals they want to spend money or need help.
    if match_patterns(q, BUYING_PATTERNS): 
        return "BUYING"
    
    if match_patterns(q, SUPPORT_PATTERNS): 
        return "SUPPORT"
    
    # ---------------------------------------------------------
    # 5. CONVERSATION CLOSERS
    # ---------------------------------------------------------
    # "Okay", "Thanks", "Bye". prevents searching the DB for these words.
    if match_patterns(q, CLOSING_PATTERNS):
        # Only treat as closing if it's short (e.g. "Okay thanks" vs "Okay I want to buy...")
        if len(q.split()) <= 4:
            return "CLOSING"

    # ---------------------------------------------------------
    # 6. PRODUCT SEARCH (Nouns & Attributes)
    # ---------------------------------------------------------
    # Checks for specific items (Heater, Tree) or attributes (Size, Price).
    # Also handles "What else?" (Continuation).
    if match_patterns(q, PRODUCT_NOUNS) or match_patterns(q, PRODUCT_ATTRIBUTES):
        return "PRODUCT_INFO"
    
    if match_patterns(q, CONTINUATION_PATTERNS):
        return "PRODUCT_INFO"

    # ---------------------------------------------------------
    # 7. CASUAL BROWSING (Short Input Fallback)
    # ---------------------------------------------------------
    # If it's a short message (1-3 words) and matched nothing else, 
    # assume it's a greeting or vague browsing.
    if len(q.split()) <= 3:
        return "BROWSING"

    # ---------------------------------------------------------
    # 8. LLM FALLBACK (Last Resort)
    # ---------------------------------------------------------
    # If the user wrote a complex sentence we didn't catch, ask Groq.
    return llm_intent_fallback(text)


def llm_intent_fallback(message: str) -> str:
    """
    Uses Groq to classify ambiguous messages. 
    Strictly limited to Frono.uk business domains.
    """
    prompt = (
        "You are a Frono.uk business classifier. Classify this message into ONE category:\n"
        "ABOUT_BRAND, BUYING, PRODUCT_INFO, SUPPORT, CLOSING, BROWSING, AFFIRMATION.\n"
        "If the message is NOT about retail, heaters, Christmas, garden furniture, or customer support, "
        "reply ONLY with 'OUT_OF_DOMAIN'.\n\n"
        f"Message: {message}"
    )

    try:
        result = llama.generate(prompt).upper()
        
        # Explicit check for domain restriction
        if "OUT_OF_DOMAIN" in result:
            return "OUT_OF_DOMAIN"

        valid_intents = [
            "ABOUT_BRAND", "BUYING", "PRODUCT_INFO", "SUPPORT", 
            "CLOSING", "BROWSING", "AFFIRMATION", "LEAD_SUBMISSION"
        ]

        for intent in valid_intents:
            if intent in result:
                return intent     
    except Exception as e:
        print(f"Intent Fallback Error: {e}")
    
    # If it's a long complex message that matched nothing, it's likely out of domain
    return "OUT_OF_DOMAIN" if len(message.split()) > 10 else "BROWSING"
