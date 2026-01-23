from queue import Queue
from fastapi.responses import StreamingResponse

stream_queue = Queue()

from fastapi import FastAPI, BackgroundTasks  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.responses import StreamingResponse
import json
import time
from models.schemas import PromptRequest, LeadCreate, LeadResponse
from llm.llama_client import LLaMAClient
from agent.health import check_health

from agent.intent_detector import detect_intent
from agent.lead_scoring import score_lead
from agent.response_strategy import next_action
from agent.rag_prompt import build_prompt
from search.retriever import retrieve_context
from search.leads_repo import create_lead

from services.email_service import send_email
from services.email_templates import (
    customer_confirmation_email,
    sales_notification_email
)
from config import SALES_EMAIL

# ---------------------------------------------------
# APP INIT
# ---------------------------------------------------
app = FastAPI(title="Frono AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # DEV ONLY
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llama = LLaMAClient()

# ---------------------------------------------------
# CONSTANT SYSTEM PROMPT (ANTI-HALLUCINATION)
# ---------------------------------------------------
STRICT_SYSTEM_PROMPT = (
    "You are Frono’s official AI assistant.\n"
    "Rules:\n"
    "- Do NOT assume product categories, brands, or services.\n"
    "- Do NOT invent features about the website.\n"
    "- Only use information explicitly provided in context.\n"
    "- If information is missing, ask a clarifying question.\n"
    "- Be concise and helpful."
)

# ---------------------------------------------------
# HEALTH
# ---------------------------------------------------
@app.get("/health")
def health():
    return check_health()

# ---------------------------------------------------
# TEST ENDPOINT
# ---------------------------------------------------
@app.post("/test-llama")
def test_llama(req: PromptRequest):
    response = llama.generate(
        prompt=req.prompt,
        system_prompt=STRICT_SYSTEM_PROMPT
    )
    return {"response": response}

# ---------------------------------------------------
# MAIN CHAT ENDPOINT
# ---------------------------------------------------
@app.post("/chat")
def chat(req: PromptRequest):
    intent = detect_intent(req.prompt)

    q = req.prompt.lower()

    # 🔒 HARD BRAND OVERRIDE (DO THIS FIRST)
    if "frono" in q or "about" in q:
        intent = "ABOUT"

    # 🗣️ PURE GREETINGS ONLY (NO BRAND)
    if intent in {"GREETING", "SMALLTALK"} and "frono" not in q:
        return {
            "intent": intent,
            "lead_score": 0,
            "reply": (
                "Hello! 👋 I can help you with information about Frono.uk, "
                "including products, shipping, returns, or general questions. "
                "What would you like to know?"
            ),
            "next_question": None,
            "capture_lead": False,
            "used_rag": False
        }

    # 🔍 ALWAYS RUN RAG FOR BRAND / INFO
    context = retrieve_context(
        query=req.prompt,
        intent=intent
    )

    final_prompt = build_prompt(
        user_message=req.prompt,
        context=context,
        intent=intent
    )

    reply = llama.generate(
        prompt=final_prompt,
        system_prompt=STRICT_SYSTEM_PROMPT
    )

    return {
        "intent": intent,
        "lead_score": 0,
        "reply": reply,
        "next_question": None,
        "capture_lead": False,
        "used_rag": bool(context)
    }

# ---------------------------------------------------
# LEAD CAPTURE + EMAIL AUTOMATION
# ---------------------------------------------------
@app.post("/lead", response_model=LeadResponse)
def capture_lead(
    lead: LeadCreate,
    background_tasks: BackgroundTasks
):
    result = create_lead(lead.dict())

    # EMAIL AUTOMATION (NON-BLOCKING)
    if lead.email and lead.consent:
        background_tasks.add_task(
            send_email,
            lead.email,
            "Thanks for contacting Frono",
            customer_confirmation_email()
        )

        background_tasks.add_task(
            send_email,
            SALES_EMAIL,
            "New Lead Captured",
            sales_notification_email(
                email=lead.email,
                intent=lead.intent,
                score=lead.lead_score
            )
        )

    return result



@app.post("/chat/stream")
def chat_stream(req: PromptRequest):
    intent = detect_intent(req.prompt)

    # Browsing intent
    if intent == "BROWSING":
        for token in llama.stream(
            prompt=(
                "The user is browsing without a clear goal.\n"
                "Politely ask one clarifying question.\n\n"
                f"User: {req.prompt}"
            ),
            system_prompt=STRICT_SYSTEM_PROMPT
        ):
            stream_queue.put(token)

        stream_queue.put("__END__")
        return {"status": "started"}

    # Non-browsing (RAG)
    context = retrieve_context(
        query=req.prompt,
        intent=intent
    )

    final_prompt = build_prompt(
        user_message=req.prompt,
        context=context,
        intent=intent
    )

    for token in llama.stream(
        prompt=final_prompt,
        system_prompt=STRICT_SYSTEM_PROMPT
    ):
        stream_queue.put(token)

    stream_queue.put("__END__")
    return {"status": "started"}


@app.get("/chat/stream/events")
def chat_stream_events():

    def event_generator():
        while True:
            token = stream_queue.get()

            if token == "__END__":
                yield "event: end\ndata: END\n\n"
                break

            yield f"data: {token}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
