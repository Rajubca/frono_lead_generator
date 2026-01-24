from pydantic import BaseModel, EmailStr, model_validator
from typing import Optional
from datetime import datetime


class PromptRequest(BaseModel):
    prompt: str


class LeadCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    intent: str
    lead_score: int

    source: str = "shopify_chat"
    page_url: Optional[str] = None
    consent: bool = False

    @model_validator(mode="after")
    def validate_contact_and_consent(self):
        # Require at least one contact method
        if not self.email and not self.phone:
            raise ValueError(
                "At least one contact method (email or phone) is required."
            )

        # GDPR: email requires consent
        if self.email and not self.consent:
            raise ValueError(
                "Consent is required when email is provided."
            )

        return self


class LeadResponse(BaseModel):
    id: str
    created_at: datetime
