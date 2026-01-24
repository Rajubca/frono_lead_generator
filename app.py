import uuid
import time
import re
from queue import Queue
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# --- IMPORTS ---
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
@app.post("/chat")
def chat(req: PromptRequest):
    intent = detect_intent(req.prompt)
    q = req.prompt.lower()

    # 🔒 HARD BRAND OVERRIDE
    if "frono" in q or "about" in q:
        intent = "ABOUT"

    # 🗣️ PURE GREETINGS
    if intent in {"GREETING", "SMALLTALK"} and "frono" not in q:
        return {
            "intent": intent,
            "lead_score": 0,
            "reply": (
                f"Hello! 👋 I am {BOT_NAME}. I can help you with Frono.uk products, "
                "shipping, or returns. What would you like to know?"
            ),
            "next_question": None,
            "capture_lead": False,
            "used_rag": False
        }

    # 🔍 RAG LOGIC
    context = retrieve_context(query=req.prompt, intent=intent)
    
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
# CHAT STREAM ENDPOINT (WRITES TO SPECIFIC QUEUE)
# ---------------------------------------------------
# In app.py

@app.post("/chat/stream")
def chat_stream(req: PromptRequest):
    session_id = req.session_id
    
    # Ensure a queue exists for this user
    if session_id not in user_queues:
        user_queues[session_id] = Queue()

    user_queue = user_queues[session_id]

    # 1. Detect Intent
    intent = detect_intent(req.prompt)
    
    # --- NEW: Handle "Okay/Thanks/Bye" Instantly ---
    if intent == "CLOSING":
        reply = "You're welcome! Feel free to ask if you need anything else. 👋"
        user_queue.put(reply)
        user_queue.put("__END__")
        return {"status": "finished_early"}
    # -----------------------------------------------

    # 2. Retrieve Context (Only runs if not CLOSING)
    context = retrieve_context(req.prompt, intent)

    # 3. Build Prompt based on Intent
    if intent == "BROWSING":
        final_prompt = (
            f"You are {BOT_NAME}, the friendly shop assistant for Frono.uk.\n"
            f"Store Context: {context}\n"
            f"User Input: '{req.prompt}'\n\n"
            "Instructions:\n"
            "1. If HELLO/HI: Welcome them warmly and mention ONE popular category (like Garden).\n"
            "2. If FEEDBACK (Nice, Great, OK): Say thanks and ask if they need anything else.\n"
            "3. If PRODUCT NAME (e.g., Laptops): Politely say we don't sell that (check Context) and suggest our actual products.\n"
            "Keep your reply natural and under 2 sentences."
        )
    else:
        # Standard RAG prompt
        final_prompt = build_prompt(
            user_message=req.prompt,
            context=context,
            intent=intent
        )

    # 4. Stream Tokens into the USER-SPECIFIC queue
    for token in llama.stream(prompt=final_prompt, system_prompt=STRICT_SYSTEM_PROMPT):
        user_queue.put(token)

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
