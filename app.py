
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
from services.stock_service import StockService
from models.schemas import LeadCreate, LeadResponse
from llm.llama_client import LLaMAClient
from agent.health import check_health
from agent.intent_detector import detect_intent, extract_contact_info
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
    session["history"][-1]["bot"] = reply
    # DEBUG LOGS
    print(f"DEBUG: Session Stage: {session.get('stage')}")
    print(f"DEBUG: Order in Cache: {stock_reservations.get(req.session_id)}")
    # -----------------------------
    # Auto Send Email on Order
    # -----------------------------
    if session["stage"] == "converted" and session.get("email"):
        order = stock_reservations.get(req.session_id)
        if not order:
            print("❌ Email logic skipped: No order found in stock_reservations.")
        elif not session.get("email"):
            print("❌ Email logic skipped: No email address in session.")
        else:
            # ✅ This block should now run reliably
            print(f"📧 Triggering email for {session['email']}...")
        if order:
            # 1 Updated stock commit logic in app.py
            # ✅ Replace the failing client.update with this:
            try:
                # Inside your chat_stream when an order is confirmed:
                StockService.reserve_and_commit(
                    sku=order["sku"],
                    qty=order["qty"]
                )

                print(f"✅ Stock committed for {order['sku']}")
            except Exception as e:
                print(f"❌ Stock update failed: {e}")


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

            # 3️⃣ Send sales notification (Fixed: now goes to SALES_EMAIL)
            background_tasks.add_task(
                send_email,
                SALES_EMAIL,
                "New Order Received",
                sales_notification_email(
                    email=session["email"],
                    intent="ORDER_PLACED",
                    score=scorer.score
                )
            )

            # 4️⃣ Cleanup (MOVED INSIDE THE IF BLOCK)
            stock_reservations.pop(req.session_id, None)
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
    session_id = req.session_id

    # ------------------------------------------------
    # 1. Initialize Session
    # ------------------------------------------------
    if session_id not in user_sessions:
        user_sessions[session_id] = {
            "stage": "browsing",
            "last_topic": None,
            "selected_product": None,   # ✅ LOCK PRODUCT
            "scorer": LeadScorer(),
            "history": [],
            "email": None,
            "menu": {},
            "stock_confirmed": False,
            "reserved_qty": None,
            "order": None,
        }

    session = user_sessions[session_id]
    scorer = session["scorer"]

    # ------------------------------------------------
    # 2. Normalize Menu Input
    # ------------------------------------------------
    clean_prompt = req.prompt.strip()

    if clean_prompt.isdigit() and len(clean_prompt) <= 2:
        menu = session.get("menu", {})
        if clean_prompt in menu:
            req.prompt = menu[clean_prompt]

    # ------------------------------------------------
    # 3. Detect Intent + Contact
    # ------------------------------------------------
    intent = detect_intent(req.prompt)
    contact = extract_contact_info(req.prompt)

    # ✅ Regex fallback for email
    email_match = re.search(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        req.prompt
    )

    if email_match and "email" not in contact:
        contact["email"] = email_match.group()

    # ------------------------------------------------
    # 4. Extract Quantity
    # ------------------------------------------------
    qty_match = re.search(r"\b(\d+)\b", req.prompt)

    requested_qty = int(qty_match.group(1)) if qty_match else (
        session.get("reserved_qty") or 1
    )

    # ------------------------------------------------
    # 5. Update Topic (ONLY IF PRODUCT KEYWORD)
    # ------------------------------------------------
    topic = extract_topic(req.prompt)

    VALID_PRODUCTS = [
        "oil filled",
        "radiator",
        "quartz",
        "fan heater",
        "halogen",
        "heater"
    ]

    if topic in VALID_PRODUCTS:
        session["last_topic"] = topic

    # ------------------------------------------------
    # 6. Resolve Product (Re-lock on Topic Change)
    # ------------------------------------------------

    product = None

    if session.get("last_topic"):

        latest_product = get_product_by_name(session["last_topic"])

        # If user changed product → reset previous order
        if latest_product:

            if (
                not session.get("selected_product")
                or session["selected_product"]["sku"] != latest_product["sku"]
            ):

                # 🔄 Reset old checkout
                session["selected_product"] = latest_product
                session["stock_confirmed"] = False
                session["order"] = None
                session["reserved_qty"] = None

                # Also clear old reservation
                stock_reservations.pop(session_id, None)

            product = session["selected_product"]


    # ------------------------------------------------
    # 7. Reserve Stock ONLY ON BUY
    # ------------------------------------------------
    context = ""
    lead_hook = None

    if intent == "BUYING" and not session["stock_confirmed"]:

        if product:

            available = product.get("qty", 0)

            if available >= requested_qty:

                order = {
                    "sku": product["sku"],
                    "name": product["name"],
                    "price": product["price"],
                    "qty": requested_qty,
                    "available": available,
                }

                stock_reservations[session_id] = order
                session["order"] = order

                session["stock_confirmed"] = True
                session["reserved_qty"] = requested_qty
                session["stage"] = "checkout"

                context = (
                    f"CONFIRMED: {product['name']} is available. "
                    f"Price: £{product['price']}."
                )

            else:
                session["stage"] = "interest"

                context = (
                    f"NOTICE: Only {available} units left. "
                    f"You requested {requested_qty}."
                )

        else:
            context = "I couldn't identify the product. Please specify again."

    else:
        context = retrieve_context(req.prompt, intent)

    # ------------------------------------------------
    # 8. Convert When Email Arrives
    # ------------------------------------------------
    if (
        "email" in contact
        and session["stock_confirmed"]
        and session["order"]
        and session["stage"] not in ["converted", "completed"]
    ):

        session["email"] = contact["email"]
        scorer.email_captured = True

        session["stage"] = "converted"
        intent = "LEAD_SUBMISSION"

        print("✅ CONVERTED:", session["email"])

    # ------------------------------------------------
    # 9. Stage Control (LOCKED)
    # ------------------------------------------------
    if session["stage"] not in ["converted", "completed"]:

        if intent == "PRODUCT_INFO":
            session["stage"] = "interest"

        elif intent == "BUYING":
            session["stage"] = "checkout"

    # ------------------------------------------------
    # 10. Lead Hooks
    # ------------------------------------------------
    if session["stage"] == "converted":

        lead_hook = (
            "The order is CONFIRMED and email is sent. "
            "Thank the user and ask them to check inbox."
        )

    elif session["stage"] == "checkout" and not session["email"]:

        lead_hook = (
            "Ask ONLY for user's email for order confirmation."
        )

    elif intent == "LEAD_SUBMISSION":

        lead_hook = "Thank user and confirm order processing."

    # ------------------------------------------------
    # 11. Build History
    # ------------------------------------------------
    history_text = ""

    for turn in session["history"][-5:]:
        if turn["bot"]:
            history_text += (
                f"User: {turn['user']}\n"
                f"Assistant: {turn['bot']}\n"
            )

    final_prompt = build_prompt(
        user_message=req.prompt,
        context=context,
        intent=intent,
        lead_hook=lead_hook,
        history=history_text,
    )

    # ------------------------------------------------
    # 12. Save Turn
    # ------------------------------------------------
    session["history"].append({
        "user": req.prompt,
        "bot": None
    })

    # ------------------------------------------------
    # 13. Debug
    # ------------------------------------------------
    print("DEBUG STATE:", {
        "stage": session["stage"],
        "email": session["email"],
        "topic": session["last_topic"],
        "product": session["selected_product"]["name"]
        if session["selected_product"] else None,
        "stock": session["stock_confirmed"],
        "order": bool(session["order"])
    })

    return {
        "intent": intent,
        "final_prompt": final_prompt,
        "scorer": scorer,
        "session": session
    }
# ---------------------------------------------------

@app.post("/chat/stream")
def chat_stream(req: PromptRequest, background_tasks: BackgroundTasks):
    session_id = req.session_id

    if session_id not in user_queues:
        user_queues[session_id] = Queue()

    user_queue = user_queues[session_id]
    
    # 1. Process the message first
    result = process_message(req)
    
    # 2. Extract session and scorer IMMEDIATELY after process_message
    session = result["session"]
    scorer = result["scorer"]
    final_prompt = result["final_prompt"]

    # --- DEBUG LOGS (Now safe to use 'session') ---
    print(f"--- STREAM START CHECK ---")
    print(f"Session ID: {session_id}")
    print(f"Current Stage: {session.get('stage')}")
    # ----------------------------------------------

    full_reply = ""
    for token in llama.stream(prompt=final_prompt, system_prompt=STRICT_SYSTEM_PROMPT):
        full_reply += token
        user_queue.put(token)

    # Save the full bot response to history
    session["history"][-1]["bot"] = full_reply

    # --- EMAIL & STOCK LOGIC ---
    if session.get("stage") == "converted" and session.get("email"):
        order = stock_reservations.get(session_id)
        
        if order:
            print(f"📧 Triggering email for {session['email']}...")
            
            # 1. Update OpenSearch Stock
            try:
                StockService.reserve_and_commit(
                    sku=order["sku"],
                    qty=order["qty"]
                )

                print(f"✅ Stock committed for in Stream {order['sku']}")
                
                print(f"✅ Stock successfully updated for {order['sku']}")

            except Exception as e:
                print("❌ Stock commit failed:", e)

                session["stage"] = "failed"
                return


            # 2. Add Email Tasks
            background_tasks.add_task(
                send_email,
                session["email"],
                "Your Frono Order Confirmation",
                customer_confirmation_email(order["name"], order["qty"], order["price"])
            )
            
            background_tasks.add_task(
                send_email,
                SALES_EMAIL,
                "New Order Received",
                sales_notification_email(session["email"], "ORDER_PLACED", scorer.score)
            )

            # 3. Finalize Session
            stock_reservations.pop(session_id, None)
            session["stage"] = "completed"
        else:
            print("❌ Stage was 'converted' but no order was found in stock_reservations.")

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
            "Thank you for your interest in Frono.uk! Our team will contact you shortly."
        )

        # background_tasks.add_task(
        #     send_email,
        #     SALES_EMAIL,
        #     "New Lead Captured",
        #     sales_notification_email(
        #         email=lead.email,
        #         intent=lead.intent,
        #         score=lead.lead_score
        #     )
        # )

    return result
