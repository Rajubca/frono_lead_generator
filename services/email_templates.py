def customer_confirmation_email():
    return (
        "Hi,\n\n"
        "Thanks for contacting Frono! 👋\n\n"
        "Our team has received your request and will reach out shortly "
        "to help you with the best product options.\n\n"
        "Best regards,\n"
        "Team Frono"
    )


def sales_notification_email(email: str, intent: str, score: int):
    return (
        "New lead captured\n\n"
        f"Email: {email}\n"
        f"Intent: {intent}\n"
        f"Lead Score: {score}\n\n"
        "Check OpenSearch for full context."
    )
