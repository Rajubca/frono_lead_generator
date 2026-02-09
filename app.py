
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
from admin.config_manager import ConfigManager
from admin.routes import admin_router
from admin.config_manager import create_config_index


# Inside process_message or chat
no_data_msg = ConfigManager.get_setting("safe_no_data_reply", "Sorry, I can't help with that.")
# ---------------------------------------------------
# GLOBAL STORE FOR MULTI-USER QUEUES
# ---------------------------------------------------
# Dictionary to hold a unique queue for each connected user session.
# Format: { "session_id": Queue() }
SAFE_NO_DATA_REPLY = (
    "I don’t have verified information for that yet. "
    "Could you please contact support@frono.uk or clarify the product, category, or SKU?"
)

user_queues = {}

# Temporary stock reservations (session-based)
stock_reservations = {}
RESERVE_TIMEOUT = 600  # 10 minutes

# ---------------------------------------------------
# APP INIT
# ---------------------------------------------------
app = FastAPI(title="Frono AI Agent") # type: ignore
app.include_router(admin_router)
app.add_middleware(
    CORSMiddleware, # type: ignore
    allow_origins=["*"],  # Adjust for production security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.on_event("startup")
async def startup_event():
    # This runs once when the server starts
    create_config_index()
# llama = LLaMAClient()
llama = GroqClient()

# ---------------------------------------------------
# UPDATED SCHEMA (Now requires session_id)
# ---------------------------------------------------
class PromptRequest(BaseModel): # type: ignore
    prompt: str
    session_id: str  # <--- NEW: Client must send their unique ID


@app.get("/admin/settings")
def get_settings():
    return ConfigManager._cache

@app.post("/admin/settings/update")
def update_setting(key: str, value: str):
    # If it's a number, try to convert it
    if value.isdigit():
        value = int(value)
        
    client.index(
        index="frono_configs",
        id=key,
        body={"key": key, "value": value, "updated_at": time.time()},
        refresh=True
    )
    ConfigManager._refresh_cache()
    return {"status": "updated", "key": key, "new_value": value}

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

    if req.prompt.lower() in {"show more", "more", "next"}:
        intent = "PRODUCT_INFO"

    # 🔓 Allow policy-related queries to pass through
    policy_keywords = ["delivery", "shipping", "return", "refund", "warranty", "policy"]

    if any(k in req.prompt.lower() for k in policy_keywords):
        intent = "POLICY_QUERY"

    # --- NEW: DOMAIN GUARDRAIL ---
    from search.retriever import get_all_collections

    collections = get_all_collections()

    if intent == "OUT_OF_DOMAIN" and not any(
        col.lower() in req.prompt.lower()
        for col in collections
    ):


        # Force a specific prompt that mandates the contact message
        final_prompt = (
            "The user asked something outside Frono's business scope. "
            "Reply EXACTLY with : 'I’m unable to find the right information for this at the moment. Please reach out to support@frono.uk, and they’ll be happy to help you.Meanwhile, feel free to explore our latest Christmas specials, heaters, and outdoor products for great deals!' "
            "Do not provide any other information or help."
        )
        # ✅ Add this turn to history so the stream endpoint doesn't crash
        session["history"].append({
            "user": req.prompt,
            "bot": None
        })
        return {
            "intent": "OUT_OF_DOMAIN",
            "final_prompt": final_prompt,
            "scorer": session["scorer"],
            "session": session
        }
    
    # ✅ ADD THIS LINE to calculate the score based on the message
    scorer.update(intent, req.prompt)
    # -----------------------------
    contact = extract_contact_info(req.prompt)

    # ✅ Regex fallback for email
    email_match = re.search(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        req.prompt
    )

    if email_match and "email" not in contact:
        contact["email"] = email_match.group()
    # 8️⃣ Convert When Email Arrives (MOVE THIS UP)
    if (
        "email" in contact
        and session.get("selected_product")
        and session["stage"] in ["interest", "checkout"]
    ):
        session["email"] = contact["email"]
        scorer.email_captured = True

        session["stage"] = "converted"
        intent = "LEAD_SUBMISSION"

        return {
            "intent": intent,
            "final_prompt": (
                "Thank you! ✅\n\n"
                "Your order for **"
                f"{session['selected_product']['name']}** has been received.\n"
                "Please check your email for confirmation."
            ),
            "scorer": scorer,
            "session": session
        }

    # ------------------------------------------------
    # 4. Extract Quantity
    # ------------------------------------------------
    qty_match = re.search(r"\b(\d+)\b", req.prompt)

    requested_qty = int(qty_match.group(1)) if qty_match else (
        session.get("reserved_qty") or 1
    )

    


    # ------------------------------------------------
    # 6. Resolve Product (SINGLE SOURCE OF TRUTH)
    # ------------------------------------------------
    product = None

    # Try resolving product directly from the user message
    latest_product = get_product_by_name(req.prompt)

    if latest_product:
        # Reset checkout if product changed
        if (
            not session.get("selected_product")
            or session["selected_product"]["sku"] != latest_product["sku"]
        ):
            session["selected_product"] = latest_product
            session["stock_confirmed"] = False
            session["order"] = None
            session["reserved_qty"] = None

            stock_reservations.pop(session_id, None)

        product = session["selected_product"]


    # ------------------------------------------------
    # 7. Reserve Stock ONLY ON BUY
    # ------------------------------------------------
    context = None
    lead_hook = None
    
    # ------------------------------------------------
    # 1️⃣ EMAIL / LEAD SUBMISSION — HARD STOP
    # ------------------------------------------------
    if intent == "LEAD_SUBMISSION" and session.get("selected_product"):
        context = (
            f"Thank you! ✅\n\n"
            f"Your order for **{session['selected_product']['name']}** "
            f"is being processed.\n"
            "Please check your email for confirmation."
        )
        return {
            "intent": intent,
            "final_prompt": context,
            "scorer": scorer,
            "session": session
        }

    # ------------------------------------------------
    # 2️⃣ BUYING FLOW — STOCK RESERVATION
    # ------------------------------------------------
    if intent == "BUYING" and not session["stock_confirmed"]:

        # 🔐 Always fall back to selected product
        product = product or session.get("selected_product")

        if product:
            session["selected_product"] = product
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
                    f"CONFIRMED: **{product['name']}** is available.\n"
                    f"Price: £{product['price']}.\n\n"
                    "Please provide your email address to continue."
                )
            else:
                session["stage"] = "interest"
                context = (
                    f"NOTICE: Only {available} units left. "
                    f"You requested {requested_qty}."
                )
        else:
            context = (
                "Please confirm which product you would like to buy."
            )

    # ------------------------------------------------
    # 3️⃣ NORMAL BROWSING / INFO
    # ------------------------------------------------
    else:
        context = retrieve_context(req.prompt, intent,session=session)



    # 🔐 TRUTH GATE — NO VERIFIED DATA
    if not context:
        session["history"].append({
            "user": req.prompt,
            "bot": SAFE_NO_DATA_REPLY
        })

        return {
            "intent": intent,
            "final_prompt": SAFE_NO_DATA_REPLY,
            "scorer": scorer,
            "session": session
        }


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

        # elif intent == "BUYING":
        #     session["stage"] = "checkout"

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
    # ✅ Safe update: check if list is not empty
    if session.get("history"):
        session["history"][-1]["bot"] = full_reply
    else:
        # Fallback if history was somehow skipped
        session["history"].append({"user": req.prompt, "bot": full_reply})

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
