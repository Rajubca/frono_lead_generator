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
