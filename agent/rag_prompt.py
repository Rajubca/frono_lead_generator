def build_prompt(user_message: str, context: str, intent: str) -> str:

    if intent == "ABOUT_BRAND":
        return f"""
You represent the company Frono.

Rules:
- Speak ONLY about Frono, never about yourself.
- Use ONLY the facts below.
- Do NOT speculate.
- Do NOT mention missing context.

FACTS ABOUT FRONO:
{context}

USER QUESTION:
{user_message}

ANSWER:
"""

    # Default behavior (products, buying, etc.)
    return f"""
You are a concise ecommerce assistant.

Use the following information if relevant:
{context}

User:
{user_message}

Answer:
"""
