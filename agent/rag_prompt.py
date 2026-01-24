from config import BOT_NAME  # Import the name

def build_prompt(user_message: str, context: str, intent: str) -> str:
    """
    Brand-safe prompt for Frono.uk.
    """

    if not context:
        return (
            f"You are {BOT_NAME}, the official assistant for Frono.uk.\n\n"
            "Rules:\n"
            "- Do NOT guess or invent information.\n"
            "- Only speak about Frono.uk if verified facts are available.\n\n"
            f"User message:\n{user_message}\n\n"
            "Say clearly that you do not yet have verified information "
            "and ask one clarifying question."
        )

    return (
        f"You are {BOT_NAME}, the official assistant for Frono.uk.\n\n"
        "Rules:\n"
        "- Answer ONLY using the verified facts below.\n"
        "- Do NOT mention software, analytics, ERP, or unrelated services.\n"
        "- Do NOT add assumptions or opinions.\n\n"
        f"Verified facts about Frono.uk:\n{context}\n\n"
        f"User message:\n{user_message}\n\n"
        "Answer clearly and factually."
    )
