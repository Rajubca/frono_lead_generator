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


# SMTP (recommended first)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "no-reply@frono.uk"
SMTP_PASSWORD = "APP_PASSWORD_HERE"
FROM_EMAIL = "Frono <no-reply@frono.uk>"

# Internal notification
SALES_EMAIL = "sales@frono.uk"
