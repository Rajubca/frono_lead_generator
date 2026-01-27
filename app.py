
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
# from fastapi import BackgroundTasks
from services.email_service import send_email
from services.email_templates import (
    customer_confirmation_email,
    sales_notification_email
)

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
app = FastAPI(title="Frono AI Agent") # type: ignore

app.add_middleware(
    CORSMiddleware, # type: ignore
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
class PromptRequest(BaseModel): # type: ignore
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

    text = text.lower()

    keywords = [
        "oil filled",
        "radiator",
        "quartz",
        "fan heater",
        "halogen",
        "heater",
        "led",
        "parcel",
        "light",
        "tree"
    ]

    for k in keywords:
        if k in text:
            return k

    return text



@app.post("/chat")
def chat(req: PromptRequest, background_tasks: BackgroundTasks):

    result = process_message(req)

    reply = llama.generate(
        prompt=result["final_prompt"],
        system_prompt=STRICT_SYSTEM_PROMPT
    )

    session = result["session"]
    scorer = result["scorer"]

    # Save reply
    session["history"][-1]["bot"] = reply

    # -----------------------------
    # Auto Send Email on Order
    # -----------------------------
    if session["stage"] == "converted" and session.get("email"):

        order = stock_reservations.get(req.session_id)

        if order:

            # 1️⃣ Commit stock
            try:
                client.update(
                    index="frono_products",
                    id=order["sku"],
                    body={
                        "script": {
                            "source": """
                                if (ctx._source.qty >= params.q) {
                                    ctx._source.qty -= params.q
                                }
                            """,
                            "params": {"q": order["qty"]}
                        }
                    }
                )
            except Exception as e:
                print("Stock commit failed:", e)

            # 2️⃣ Send customer email
            background_tasks.add_task(
                send_email,
                session["email"],
                "Your Frono Order Confirmation",
                customer_confirmation_email(
                    product=order["name"],
                    qty=order["qty"],
                    price=order["price"]
                )
            )

            # 3️⃣ Send sales email
            background_tasks.add_task(
                send_email,
                SALES_EMAIL,
                "New Order Received",
                sales_notification_email(
                    email=session["email"],
                    intent="ORDER",
                    score=scorer.score
                )
            )

            # 4️⃣ Cleanup AFTER success
            # stock_reservations.pop(req.session_id, None)

            session["stage"] = "completed"

    return {
        "intent": result["intent"],
        "reply": reply,
        "lead_score": scorer.score
    }


# ---------------------------------------------------
# CHAT STREAM ENDPOINT (WRITES TO SPECIFIC QUEUE)
# ---------------------------------------------------
def process_message(req: PromptRequest):

    # -------------------------
    # Default safe context
    # -------------------------
    context = ""

    session_id = req.session_id

    # -------------------------
    # Init session
    # -------------------------
    if session_id not in user_sessions:
        user_sessions[session_id] = {
            "stage": "browsing",
            "last_topic": None,
            "scorer": LeadScorer(),
            "history": [],
            "email": None,
            "menu": {},
            "stock_confirmed": False,
            "reserved_qty": None
        }

    session = user_sessions[session_id]
    scorer = session["scorer"]

    # -------------------------
    # Build Menus
    # -------------------------
    prompt_lower = req.prompt.lower()

    if "heater" in prompt_lower:

        session["menu"] = {
            "1": "oil filled radiator",
            "2": "quartz heater",
            "3": "fan heater",
            "4": "halogen heater"
        }

    elif "light" in prompt_lower:

        session["menu"] = {
            "1": "led parcel lights",
            "2": "rope lights",
            "3": "curtain lights",
            "4": "twig tree lights"
        }

    # -------------------------
    # Save User Message
    # -------------------------
    session["history"].append({
        "user": req.prompt,
        "bot": None
    })

    session["history"] = session["history"][-6:]

    # -------------------------
    # Resolve Menu Selection
    # -------------------------
    clean = req.prompt.strip()

    if clean.isdigit():

        menu = session.get("menu", {})

        if clean in menu:

            req = PromptRequest(
                prompt=menu[clean],
                session_id=req.session_id
            )

            prompt_lower = req.prompt.lower()

    # -------------------------
    # Detect Intent
    # -------------------------
    intent = detect_intent(req.prompt)

    
    # -------------------------
    # Extract Email + Qty Together
    # -------------------------

    # Extract quantity FIRST
    qty_match = re.search(r"\b(\d+)\b", req.prompt.lower())

    if qty_match:
        session["reserved_qty"] = int(qty_match.group(1))


    # Extract email
    email_match = re.search(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        req.prompt
    )

    if email_match:
        session["email"] = email_match.group(0)
        scorer.email_captured = True
        intent = "LEAD_SUBMISSION"


    if email_match:

        session["email"] = email_match.group(0)
        scorer.email_captured = True
        intent = "LEAD_SUBMISSION"

    # -------------------------
    # Funnel Stages
    # -------------------------
    if intent == "PRODUCT_INFO":
        session["stage"] = "interest"

    elif intent == "BUYING":
        session["stage"] = "checkout"

    # Always update topic
    if intent in ["PRODUCT_INFO", "BUYING", "AFFIRMATION"]:
        session["last_topic"] = extract_topic(req.prompt)

    # -------------------------
    # Re-confirm Reservation on YES
    # -------------------------
    if (
        intent == "AFFIRMATION"
        and session["last_topic"]
        and session_id not in stock_reservations
    ):

        product = get_product_by_name(session["last_topic"])

        if product and product["qty"] > 0:

            qty = session.get("reserved_qty")

            if not qty:
                qty = 1


            stock_reservations[session_id] = {
                "sku": product["sku"],
                "name": product["name"],
                "price": product["price"],
                "qty": qty,
                "available": product["qty"],
                "time": time.time()
            }

            session["stock_confirmed"] = True
            session["stage"] = "checkout"

    # -------------------------
    # Quantity Detection
    # -------------------------
    qty_match = re.search(r"\b(\d+)\b", req.prompt.lower())

    if qty_match and intent in ["BUYING", "AFFIRMATION", "PRODUCT_INFO"]:

        requested_qty = int(qty_match.group(1))

        if (
            session["last_topic"]
            and session_id not in stock_reservations
        ):

            product = get_product_by_name(session["last_topic"])

            if product:

                available = product["qty"]

                if available >= requested_qty:

                    stock_reservations[session_id] = {
                        "sku": product["sku"],
                        "name": product["name"],
                        "price": product["price"],
                        "qty": requested_qty,
                        "available": available,
                        "time": time.time()
                    }

                    session["stock_confirmed"] = True
                    session["reserved_qty"] = requested_qty
                    session["stage"] = "checkout"

                else:

                    session["stage"] = "interest"

                    context = (
                        f"Sorry, only {available} units are available."
                    )

    # -------------------------
    # Commit Order (After Email)
    # -------------------------
    if intent == "LEAD_SUBMISSION" and session["email"]:

        order = stock_reservations.get(session_id)

        if not order:

            session["stage"] = "interest"

            context = (
                "Your order session expired. "
                "Please select the product again."
            )

        else:

            session["stage"] = "converted"

            # Commit stock
            try:

                client.update(
                    index="frono_products",
                    id=order["sku"],
                    body={
                        "script": {
                            "source": """
                            if (ctx._source.qty >= params.q) {
                                ctx._source.qty -= params.q
                            }
                            """,
                            "params": {"q": order["qty"]}
                        }
                    }
                )

            except Exception as e:
                print("Stock commit failed:", e)

            # Remove reservation
            stock_reservations.pop(session_id, None)

            qty = order.get("qty") or 1
            price = order.get("price") or 0

            total = price * qty


            context = (
                f"Order confirmed.\n"
                f"Product: {order['name']}\n"
                f"Quantity: {order['qty']}\n"
                f"Total: £{total}\n\n"
                "Thank you for your purchase."
            )

            # Reset session
            session["last_topic"] = None
            session["stock_confirmed"] = False
            session["reserved_qty"] = None
            session["menu"] = {}

    # -------------------------
    # Normal Context
    # -------------------------
    else:

        if session.get("stock_confirmed") and session_id in stock_reservations:

            order = stock_reservations[session_id]

            context = (
                f"Stock confirmed.\n"
                f"Product: {order['name']}\n"
                f"Available: {order['available']}\n"
                f"Reserved: {order['qty']}\n"
                f"Price: £{order['price']}\n"
                f"Status: Ready for checkout."
            )

        else:

            context = retrieve_context(
                query=req.prompt,
                intent=intent
            )

    # -------------------------
    # Lead Hook (Ask Email)
    # -------------------------
    lead_hook = None

    if session["stage"] == "checkout" and not scorer.email_captured:

        lead_hook = (
            "Please provide your email address "
            "to complete your order."
        )

    # -------------------------
    # Build History
    # -------------------------
    history_text = ""

    for turn in session["history"][:-1]:

        if turn["bot"]:

            history_text += (
                f"User: {turn['user']}\n"
                f"Assistant: {turn['bot']}\n"
            )

    # -------------------------
    # Build Prompt
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

    return StreamingResponse( # type: ignore
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
# from fastapi import BackgroundTasks

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
