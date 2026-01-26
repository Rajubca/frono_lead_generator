import uuid
import time
import re
from queue import Queue
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# --- IMPORTS ---
from agent.lead_scoring import LeadScorer
from agent.response_strategy import get_lead_hook

from models.schemas import LeadCreate, LeadResponse
from llm.llama_client import LLaMAClient
from agent.health import check_health
from agent.intent_detector import detect_intent
from agent.rag_prompt import build_prompt
from search.retriever import retrieve_context
from search.leads_repo import create_lead
from services.email_service import send_email
from services.email_templates import customer_confirmation_email, sales_notification_email
from config import SALES_EMAIL, BOT_NAME, STRICT_SYSTEM_PROMPT
from llm.groq_client import GroqClient # WAS: from llm.llama_client import LLaMAClient
# ---------------------------------------------------
# GLOBAL STORE FOR MULTI-USER QUEUES
# ---------------------------------------------------
# Dictionary to hold a unique queue for each connected user session.
# Format: { "session_id": Queue() }
user_queues = {}

# ---------------------------------------------------
# APP INIT
# ---------------------------------------------------
app = FastAPI(title="Frono AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# llama = LLaMAClient()
llama = GroqClient()

# ---------------------------------------------------
# UPDATED SCHEMA (Now requires session_id)
# ---------------------------------------------------
class PromptRequest(BaseModel):
    prompt: str
    session_id: str  # <--- NEW: Client must send their unique ID

# ---------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------
@app.get("/health")
def health():
    return check_health()

# ---------------------------------------------------
# TEST ENDPOINT (Optional Debugging)
# ---------------------------------------------------
@app.post("/test-llama")
def test_llama(req: PromptRequest):
    response = llama.generate(
        prompt=req.prompt,
        system_prompt=STRICT_SYSTEM_PROMPT
    )
    return {"response": response}

# ---------------------------------------------------
# MAIN CHAT ENDPOINT (Standard REST - Non-Streaming)
# ---------------------------------------------------


# Global store for context memory (In production, use Redis)

user_sessions = {} 
def extract_topic(text):
    keywords = ["heater","tree","light","furniture","pool"]
    for k in keywords:
        if k in text.lower():
            return k
    return text

@app.post("/chat")
def chat(req: PromptRequest):

    result = process_message(req)

    reply = llama.generate(
        prompt=result["final_prompt"],
        system_prompt=STRICT_SYSTEM_PROMPT
    )

    # Fill placeholder
    session = result["session"]
    session["history"][-1]["bot"] = reply

    return {
        "intent": result["intent"],
        "reply": reply,
        "lead_score": result["scorer"].score
    }


# ---------------------------------------------------
# CHAT STREAM ENDPOINT (WRITES TO SPECIFIC QUEUE)
# ---------------------------------------------------
def process_message(req: PromptRequest):

    session_id = req.session_id

    # -------------------------
    # Init session
    # -------------------------
    if session_id not in user_sessions:
        user_sessions[session_id] = {
            "last_topic": None,
            "scorer": LeadScorer(),
            "history": []
        }

    session = user_sessions[session_id]
    scorer = session["scorer"]

    # -------------------------
    # Save user message FIRST
    # -------------------------
    session["history"].append({
        "user": req.prompt,
        "bot": None   # placeholder
    })

    session["history"] = session["history"][-6:]

    # -------------------------
    # Detect intent
    # -------------------------
    intent = detect_intent(req.prompt)

    # -------------------------
    # Topic memory
    # -------------------------
    search_query = req.prompt

    if intent in ["PRODUCT_INFO", "BROWSING"]:
        session["last_topic"] = extract_topic(req.prompt)

    elif intent == "AFFIRMATION" and session["last_topic"]:
        if len(req.prompt.split()) <= 2:
            search_query = session["last_topic"]

    # -------------------------
    # Lead scoring
    # -------------------------
    scorer.update(intent, req.prompt)

    lead_hook = None
    if scorer.should_trigger_hook():
        lead_hook = get_lead_hook(intent)

    # -------------------------
    # Retrieve context
    # -------------------------
    context = retrieve_context(
        query=search_query,
        intent=intent
    )

    # -------------------------
    # Build conversation history
    # -------------------------
    history_text = ""

    for turn in session["history"][:-1]:  # exclude current placeholder
        if turn["bot"]:
            history_text += f"User: {turn['user']}\n"
            history_text += f"Assistant: {turn['bot']}\n"

    # -------------------------
    # Build prompt
    # -------------------------
    final_prompt = build_prompt(
        user_message=req.prompt,
        context=context,
        intent=intent,
        lead_hook=lead_hook,
        history=history_text
    )

    return {
        "intent": intent,
        "final_prompt": final_prompt,
        "scorer": scorer,
        "session": session   # 👈 return session
    }

@app.post("/chat/stream")
def chat_stream(req: PromptRequest):

    session_id = req.session_id

    if session_id not in user_queues:
        user_queues[session_id] = Queue()

    user_queue = user_queues[session_id]

    result = process_message(req)

    final_prompt = result["final_prompt"]

    full_reply = ""

    for token in llama.stream(
        prompt=final_prompt,
        system_prompt=STRICT_SYSTEM_PROMPT
    ):
        full_reply += token
        user_queue.put(token)

    # Fill placeholder
    session = result["session"]
    session["history"][-1]["bot"] = full_reply

    user_queue.put("__END__")

    return {"status": "started"}


# ---------------------------------------------------
# SSE ENDPOINT (READS FROM SPECIFIC QUEUE)
# ---------------------------------------------------
@app.get("/chat/stream/events/{session_id}")
def chat_stream_events(session_id: str, request: Request):
    
    # Create queue if it doesn't exist yet
    if session_id not in user_queues:
        user_queues[session_id] = Queue()

    def event_generator():
        q = user_queues[session_id]
        
        while True:
            # Check for client disconnect (FastAPI handles this largely automatically in generator context)
            if await_client_disconnect(request):
                # Optional: Cleanup queue if client leaves
                # del user_queues[session_id] 
                break

            if not q.empty():
                token = q.get()
                
                if token == "__END__":
                    yield "event: end\ndata: END\n\n"
                    # We keep the queue alive for the session duration
                    continue 
                
                yield f"data: {token}\n\n"
            else:
                # Sleep briefly to prevent CPU spike while waiting for tokens
                time.sleep(0.05) 

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

def await_client_disconnect(request: Request):
    # Helper to check connection status if needed
    return False 

# ---------------------------------------------------
# LEAD CAPTURE + EMAIL AUTOMATION
# ---------------------------------------------------
from fastapi import BackgroundTasks

@app.post("/lead", response_model=LeadResponse)
def capture_lead(
    lead: LeadCreate,
    background_tasks: BackgroundTasks
):
    result = create_lead(lead.dict())

    # Optional: email automation
    if lead.consent:
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
