from admin.config_manager import ConfigManager

class LeadScorer:
    def __init__(self):
        self.score = 0
        self.history = []
        self.email_captured = False

    def update(self, intent: str, text: str):
        # Fetch dynamic points from Admin Config with hardcoded fallbacks
        buying_pts = int(ConfigManager.get_setting("buying_points", 20))
        affirmation_pts = int(ConfigManager.get_setting("affirmation_points", 15))
        info_pts = int(ConfigManager.get_setting("product_info_points", 10))
        closing_penalty = int(ConfigManager.get_setting("closing_penalty", -10))

        points = 0
        
        if intent == "BUYING":
            points = buying_pts
        elif intent == "AFFIRMATION":
            points = affirmation_pts
        elif intent == "PRODUCT_INFO":
            points = info_pts
        elif any(kw in text.lower() for kw in ["price", "cost"]):
            points = affirmation_pts # Reuse affirmation points for price intent
        elif intent == "CLOSING":
            points = closing_penalty
        
        self.score += points
        self.history.append(f"{intent} (+{points})")
        self.score = min(max(self.score, 0), 100)
        
        return self.score
    
    

    def should_trigger_hook(self):
        # Trigger only if "Hot" (50+) and we haven't got the email yet
        return self.score >= 50 and not self.email_captured

    def mark_captured(self):
        self.email_captured = True