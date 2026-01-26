from config import BOT_NAME


def build_prompt(user_message, context, intent, lead_hook=None, history=""):
    """
    Brand-safe, memory-aware, lead-optimized prompt builder.
    Includes conversation history and optional lead hooks.
    """

    # ----------------------------------
    # 1. Lead Hook Instruction
    # ----------------------------------
    hook_instruction = ""

    if lead_hook:
        hook_instruction = (
            f"\n- STRATEGIC GOAL: {lead_hook}\n"
            "- Work this goal into your response naturally as a helpful suggestion."
        )

    # ----------------------------------
    # 2. Conversation Memory
    # ----------------------------------
    history_block = ""

    if history.strip():
        history_block = (
            "Conversation so far:\n"
            f"{history}\n\n"
        )

    # ----------------------------------
    # 3. Fallback (No Context)
    # ----------------------------------
    if not context:
        return (
            f"You are {BOT_NAME}, the official assistant for Frono.uk.\n\n"

            f"{history_block}"

            "Rules:\n"
            "- Do NOT guess or invent information.\n"
            "- Only speak about Frono.uk if verified facts are available."
            f"{hook_instruction}\n\n"

            f"User message:\n{user_message}\n\n"

            "Say clearly that you do not yet have verified information "
            "and ask one clarifying question."
        )

    # ----------------------------------
    # 4. Main RAG Prompt (With Memory)
    # ----------------------------------
    return (
        f"You are {BOT_NAME}, the official assistant for Frono.uk.\n\n"

        f"{history_block}"

        "Rules:\n"
        "- Answer using the verified facts below."
        "- Do NOT proceed with payment unless contact is collected.\n"
        "- When the user is ready to buy, guide them through next steps."
        "- Do NOT mention software, analytics, ERP, or unrelated services.\n"
        "- Do NOT add assumptions or opinions."
        f"{hook_instruction}\n\n"

        f"Verified facts about Frono.uk:\n{context}\n\n"

        f"User message:\n{user_message}\n\n"

        "Answer clearly, naturally, and factually."
    )
