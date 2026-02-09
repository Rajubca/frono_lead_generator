# OpenSearch configuration
OPENSEARCH_URL = "http://127.0.0.1:9200"
OPENSEARCH_HOST = "127.0.0.1"
OPENSEARCH_PORT = 9200
OPENSEARCH_USE_SSL = False

# Shopify configuration
SHOPIFY_API_KEY=""
SHOPIFY_API_PASSWORD=""
SHOPIFY_ACCESS_TOKEN=""
SHOPIFY_STORE_NAME=""
API_VERSION="2025-01"

# Index names
INDEX_PRODUCTS = "frono_products"
INDEX_FAQ = "frono_faq"
INDEX_POLICIES = "frono_policies"
INDEX_LEADS = "frono_leads"
INDEX_SESSIONS = "frono_sessions"

# Llama configuration
LLAMA_MODEL = "mistral:latest"
LLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
LLAMA_MODEL = "mistral:latest"
LLAMA_TIMEOUT = 120

# GROQ Configuration (Fastest Inference)
GROQ_API_KEY = ""  # <--- PASTE YOUR KEY HERE
GROQ_MODEL = "llama-3.3-70b-versatile"  # Very fast and smart model

# Bot configuration
BOT_NAME = "Frono BuddyAI"

# SMTP (recommended first)
SMTP_HOST = "smtp.zoho.eu"
SMTP_PORT = 587
SMTP_USERNAME = "support@frono.uk"
SMTP_PASSWORD = """"""
FROM_EMAIL = "Frono <support@frono.uk>"

# Internal notification
SALES_EMAIL = "rajubca013@hotmail.com"

# ... existing config ...

# Fallback context if search fails
# Fallback context if search fails
STORE_SUMMARY = (
    "Frono.uk is a home and lifestyle store based in the UK. "
    "We focus on making your home cozy and your garden beautiful. "
    "Our key collections are: "
    "- Christmas Shop (Trees, Lights, and Decor). "
    "- Garden & Outdoor (Rattan furniture, Hot Tubs, Gazebos). "
    "- Seasonal Heating (Energy-efficient heaters). "
    "We do not sell electronics or fashion. "
    "If asked about stock, say you can check the specific category."
)

# --- SYSTEM PROMPT (Moved here so it can use BOT_NAME) ---
STRICT_SYSTEM_PROMPT = (
    f"You are {BOT_NAME}, the official AI assistant for Frono.uk.\n\n"
    "CRITICAL RULES:\n"
    "- You MUST ONLY use verified information provided in context.\n"
    "- You MUST NOT invent products, prices, stock, categories, or policies.\n"
    "- You MUST NOT assume availability or offerings.\n"
    "- If verified information is missing, say clearly that you do not know.\n"
    "- Ask a clarifying question instead of guessing.\n"
    "- Be concise, factual, and neutral.\n"
)
# ---------------------------------------------------