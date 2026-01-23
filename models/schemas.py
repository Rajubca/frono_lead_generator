from pydantic import BaseModel, EmailStr
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


class LeadResponse(BaseModel):
    id: str
    created_at: datetime
