class LeadScorer:
    def __init__(self):
        self.score = 0
        self.history = []
        self.email_captured = False

    def update(self, intent: str, text: str):
        points = 0
        
        # Scoring Rules
        if intent == "BUYING":
            points = 20
        elif intent == "AFFIRMATION": # "Yes, please"
            points = 15
        elif intent == "PRODUCT_INFO":
            points = 10
        elif "price" in text.lower() or "cost" in text.lower():
            points = 15
        
        # Penalties (to avoid nagging uninterested users)
        elif intent == "CLOSING":
            points = -10
        
        self.score += points
        self.history.append(f"{intent} (+{points})")
        
        # Cap score to prevent overflow logic
        self.score = min(max(self.score, 0), 100)
        
        return self.score

    def should_trigger_hook(self):
        # Trigger only if "Hot" (50+) and we haven't got the email yet
        return self.score >= 50 and not self.email_captured

    def mark_captured(self):
        self.email_captured = True