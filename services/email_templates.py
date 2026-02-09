def customer_confirmation_email(product, qty, price):
    print("Generating customer confirmation email...")
    total = qty * price

    return f"""
Hello,

Thank you for your order with Frono.uk.

Order Details:

Product: {product}
Quantity: {qty}
Price: £{price}
Total: £{total}

Your order is now being processed.

If you have questions, reply to this email.

Regards,
Frono Team
"""


def sales_notification_email(email: str, intent: str, score: int):
    return (
        "New lead captured\n\n"
        f"Email: {email}\n"
        f"Intent: {intent}\n"
        f"Lead Score: {score}\n\n"
        "Check OpenSearch for full context."
    )
