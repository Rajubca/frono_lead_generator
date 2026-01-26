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
from search.retriever import get_product_by_name
from search.opensearch_client import client

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
# Temporary stock reservations (session-based)
stock_reservations = {}
RESERVE_TIMEOUT = 600  # 10 minutes

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
    return text.lower().strip()


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
            "stage": "browsing",
            "last_topic": None,
            "scorer": LeadScorer(),
            "history": []
        }

    session = user_sessions[session_id]
    # Cleanup expired reservations
    now = time.time()

    for sid in list(stock_reservations.keys()):
        if now - stock_reservations[sid]["time"] > RESERVE_TIMEOUT:
            del stock_reservations[sid]

    scorer = session["scorer"]
    # Prepare history early (needed for early returns)
    history_text = ""

    for turn in session["history"]:
        if turn["bot"]:
            history_text += f"User: {turn['user']}\n"
            history_text += f"Assistant: {turn['bot']}\n"


    # -------------------------
    # Save user message FIRST
    # -------------------------
    session["history"].append({
        "user": req.prompt,
        "bot": None
    })

    session["history"] = session["history"][-6:]

    # -------------------------
    # Detect intent
    # -------------------------
    intent = detect_intent(req.prompt)

    # -------------------------
    # Funnel stage tracking
    # -------------------------
    # Funnel stage tracking (STICKY CHECKOUT)

    # ------------------------------------------------
    # Force contact before checkout progression
    # ------------------------------------------------

    if (
        session["stage"] == "checkout"
        and not scorer.email_captured
        and intent in ["PAYMENT", "CONFIRMATION", "AFFIRMATION", "BUYING"]
    ):
        intent = "NEED_CONTACT"

    if session["stage"] != "converted":

        if intent == "PRODUCT_INFO":
            session["stage"] = "interest"

        elif intent == "BUYING":
            session["stage"] = "checkout"

        # Keep checkout until completed
        elif session["stage"] == "checkout":
            session["stage"] = "checkout"


    elif intent == "LEAD_SUBMISSION":

        scorer.email_captured = True

        order = stock_reservations.get(session_id)

        # No active reservation → reset
        if not order:

            session["stage"] = "interest"

            lead_hook = None

            return {
                "intent": intent,
                "final_prompt": build_prompt(
                    user_message=req.prompt,
                    context="Your order session has expired. Please select the product again.",
                    intent=intent,
                    lead_hook=None,
                    history=history_text
                ),
                "scorer": scorer,
                "session": session
            }

        # Active reservation → commit
        session["stage"] = "converted"

        stock_reservations.pop(session_id, None)

        try:
            client.update(
                index="frono_products",
                id=order["sku"],
                body={
                    "script": {
                        "source": "if (ctx._source.qty >= params.q) { ctx._source.qty -= params.q }",
                        "params": {"q": order["qty"]}
                    }
                }
            )

        except Exception as e:
            print("Stock commit failed:", e)


        scorer.email_captured = True

        if session_id in stock_reservations:

            session["stage"] = "converted"

            order = stock_reservations.pop(session_id)

            try:
                client.update(
                    index="frono_products",
                    id=order["sku"],
                    body={
                        "script": {
                            "source": "if (ctx._source.qty >= params.q) { ctx._source.qty -= params.q }",
                            "params": {"q": order["qty"]}
                        }
                    }
                )

            except Exception as e:
                print("Stock commit failed:", e)

        else:
            session["stage"] = "interest"


            order = stock_reservations.pop(session_id)

            client.update(
                index="frono_products",
                id=order["sku"],
                body={
                    "script": {
                        "source": "ctx._source.qty -= params.q",
                        "params": {"q": order["qty"]}
                    }
                }
            )


    # -------------------------
    # Detect quantity intent
    # -------------------------
    qty_match = re.search(r"\b(\d+)\s*(unit|units|pcs|pieces)?\b", req.prompt.lower())

    if qty_match and intent in ["BUYING", "AFFIRMATION", "PRODUCT_INFO"]:


        requested_qty = int(qty_match.group(1))

        # Try reserve product
        if session["last_topic"]:

            product = get_product_by_name(session["last_topic"])


            if product and session_id not in stock_reservations:

                available = product["qty"]

                if available >= requested_qty:

                    # Reserve in memory
                    stock_reservations[session_id] = {
                        "sku": product["sku"],
                        "qty": requested_qty,
                        "time": time.time()
                    }

                    session["reserved_qty"] = requested_qty

                else:
                    session["stage"] = "interest"

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

    # -------------------------
    # Lead Capture Logic (FIXED)
    # -------------------------
    # -------------------------
    # Lead Capture Logic (STRICT)
    # -------------------------

    lead_hook = None

    # Highest priority: Must collect contact
    if intent == "NEED_CONTACT":

        lead_hook = (
            "Before continuing, ask the user clearly for their "
            "email address or phone number to proceed with the order. "
            "Do not discuss payment or delivery yet."
        )

    # Normal checkout without contact
    elif session["stage"] == "checkout" and not scorer.email_captured:

        lead_hook = (
            "Please provide your email or phone number "
            "so I can complete your order."
        )

    # Secondary: High intent lead
    elif scorer.should_trigger_hook() and intent in ["BUYING", "AFFIRMATION"]:

        lead_hook = (
            "Ask the user for their email or phone number "
            "to proceed with the order."
        )

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

    for turn in session["history"][:-1]:
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
        "session": session
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
