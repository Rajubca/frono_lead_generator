1. Project Goals

Provide accurate answers about Frono.uk

Prevent AI hallucinations or false claims

Convert guest users into qualified leads

Ensure brand safety and trust

Maintain full transparency of AI knowledge

2. High-Level Architecture
Frontend Chat Widget (HTML/JS)
        |
        v
FastAPI Backend
        |
        +-- Intent Detection
        |
        +-- Context Retrieval (OpenSearch RAG)
        |
        +-- Prompt Builder (Anti-hallucination)
        |
        +-- LLM (Ollama – Mistral)
        |
        +-- Lead Capture + Email Automation

3. Tech Stack
Backend

Python 3.11

FastAPI

Uvicorn

Requests

Ollama (local LLM runtime)

AI / Search

OpenSearch 2.x

OpenSearch Dashboards

RAG (Retrieval Augmented Generation)

Frontend

Vanilla HTML / CSS / JavaScript

Embedded Chat Widget

4. OpenSearch Indexes (Source of Truth)
4.1 frono_site_facts (CRITICAL)

This index contains verified public facts about Frono.uk.
The AI must rely on this index when answering brand or company questions.

Mapping

{
  "type": "keyword",
  "title": "text",
  "content": "text",
  "confidence": "integer",
  "source": "keyword"
}


Example Documents

Business identity & ownership

Product categories

Shipping & return policies

Contact details

Brand disambiguation (NOT ERP, NOT Furneo, NOT scam sites)

This index prevents hallucinations.

4.2 frono_products

Contains product-level data used for buying and product questions.

4.3 Other Indexes

frono_leads – captured leads

frono_sessions – user sessions (optional)

.kibana_* – dashboard metadata

5. Retrieval Logic (RAG)
retrieve_context()

Forces ABOUT / BRAND queries to pull from frono_site_facts

Uses keyword + semantic matching

Returns only verified documents

Returns empty context if nothing reliable is found

if intent in {"ABOUT", "BRAND", "GENERAL"}:
    search frono_site_facts


If no results → AI must politely refuse to guess.

6. Prompt Safety Design
build_prompt()

The prompt builder enforces:

❌ No guessing

❌ No invented services

❌ No unrelated industries

✅ Only verified Frono.uk facts

✅ Friendly, concise tone

Verified Context Exists

AI answers only using retrieved facts.

No Context Exists

AI clearly says:

“I don’t have enough verified information yet”
and asks one clarifying question.

This is the core anti-hallucination guardrail.

7. LLM Configuration (Performance + Safety)
llama_client.py

Key optimizations:

num_predict: 120 → fast responses

temperature: 0.2 → deterministic answers

Strong system prompt enforcing brand rules

Local inference (no external API latency)

Result:

⚡ Fast

🛡️ Safe

🔒 Private

8. Chat Endpoints
/chat

Standard request/response

Intent detection

RAG retrieval

Lead scoring

/chat/stream

Token streaming for typing UX

/chat/stream/events

Server-Sent Events (SSE)

Frontend receives tokens live

9. Frontend Chat Widget

Features:

Floating chat UI

Real-time responses

Email capture flow

Lead submission to backend

Brand-safe messaging

Designed to embed directly into Shopify (Frono.uk).

10. Lead Capture & Automation

When intent or score qualifies:

Email is requested

Lead stored in OpenSearch / DB

Confirmation email sent to customer

Notification email sent to sales team

All email actions run via background tasks (non-blocking).

11. How to Inspect AI Knowledge (IMPORTANT)
OpenSearch Dashboards
http://localhost:5601


Steps:

Stack Management → Index Patterns

Create pattern for frono_site_facts

Discover → Select index

View exact documents AI uses

This is the single source of truth for AI answers.

12. Why This System Is Trustworthy

AI cannot invent facts

All brand claims are verifiable

Public confusion (ERP / scam sites) is explicitly handled

Every answer is traceable to OpenSearch documents

This design is suitable for:

Production ecommerce

Compliance-sensitive brands

Long-term SEO trust

13. Future Enhancements

Confidence-weighted retrieval

Admin UI for editing site facts

Analytics on unanswered questions

Multilingual support (UK/EU)

14. Final Note

If the data in OpenSearch is correct, the AI will always be correct.

This project turns OpenSearch into a brand knowledge engine, not just search.