def next_action(intent: str) -> dict:
    if intent == "BUYING":
        return {
            "ask": "Would you like me to help you place the order or share a quick recommendation?",
            "capture_lead": True
        }

    if intent == "PRODUCT_INFO":
        return {
            "ask": "Would you like a comparison or a recommendation based on your needs?",
            "capture_lead": False
        }

    if intent == "SUPPORT":
        return {
            "ask": "Can you tell me your order number or the issue you're facing?",
            "capture_lead": False
        }

    if intent == "BROWSING":
        return {
            "ask": "No problem 🙂 What kind of products are you interested in today?",
            "capture_lead": False
        }


    return {
        "ask": "How can I assist you further?",
        "capture_lead": False
    }

def get_lead_hook(intent: str) -> str:
    """Returns a high-value hook to capture lead info based on intent."""
    if intent == "AFFIRMATION":
        return "Since you're interested, I can email you our latest catalog and a 10% discount code. What's the best email for you?"
    
    if intent == "BUYING":
        return "I can have our team send you a formal quote and delivery timeline. Would you like to provide your email or phone number?"

    if intent == "PRODUCT_INFO":
        return "Would you like the full technical specifications and a comparison guide sent to your inbox?"

    return "Would you like to stay updated with our exclusive seasonal offers? Just leave your email below!"