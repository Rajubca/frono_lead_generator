INTENT_SCORES = {
    "BUYING": 50,
    "PRODUCT_INFO": 25,
    "SUPPORT": 10,
    "BROWSING": 5,
    "UNKNOWN": 0
}

def score_lead(intent: str, questions_asked: int) -> int:
    base = INTENT_SCORES.get(intent, 0)

    # Engagement bonus
    engagement_bonus = min(questions_asked * 5, 20)

    return min(base + engagement_bonus, 100)
