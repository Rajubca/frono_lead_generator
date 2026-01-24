OPENSEARCH_URL = "http://127.0.0.1:9200"
OPENSEARCH_HOST = "127.0.0.1"
OPENSEARCH_PORT = 9200
OPENSEARCH_USE_SSL = False

INDEX_PRODUCTS = "frono_products"
INDEX_FAQ = "frono_faq"
INDEX_POLICIES = "frono_policies"
INDEX_LEADS = "frono_leads"
INDEX_SESSIONS = "frono_sessions"

# Llama configuration
LLAMA_MODEL = "mistral:latest"
LLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
LLAMA_MODEL = "mistral:latest"
LLAMA_TIMEOUT = 60

# Bot configuration
BOT_NAME = "Frono BuddyAI"

# SMTP (recommended first)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "no-reply@frono.uk"
SMTP_PASSWORD = "APP_PASSWORD_HERE"
FROM_EMAIL = "Frono <no-reply@frono.uk>"

# Internal notification
SALES_EMAIL = "sales@frono.uk"

# ... existing config ...

# Fallback context if search fails
# Fallback context if search fails
STORE_SUMMARY = (
    "Frono.uk is a home and lifestyle store based in the UK. "
    "We focus on making your home cozy and your garden beautiful. "
    "Our key collections are: "
    "- Garden & Outdoor (Rattan furniture, Hot Tubs, Gazebos). "
    "- Seasonal Heating (Energy-efficient heaters). "
    "- Christmas Shop (Trees, Lights, and Decor). "
    "We do not sell electronics or fashion. "
    "If asked about stock, say you can check the specific category."
)