"""Payment tool for processing donations via Stripe and PayPal."""

from typing import Optional, Literal
from contextvars import ContextVar

from langchain_core.tools import tool

from ..config import config
from ..stripe_service import stripe_service
from ..paypal_service import paypal_service


# Context variable to hold session payment data during request processing
# This gets set by the API before invoking the agent
payment_context: ContextVar[dict] = ContextVar("payment_context", default=None)


def get_payment_context() -> Optional[dict]:
    """Get the current payment context."""
    return payment_context.get()


def set_payment_context(ctx: dict) -> None:
    """Set the payment context for the current request."""
    payment_context.set(ctx)


@tool
def payment_tool(
    action: str,
    amount: Optional[float] = None,
    description: Optional[str] = None,
    user_confirmation: bool = False,
    donor_email: Optional[str] = None,
    payment_method: Optional[str] = None,
) -> str:
    """MANDATORY: Call this IMMEDIATELY when user mentions donate/donation/contribute.

    DO NOT ask permission. DO NOT provide links first. CALL THIS TOOL FIRST.

    Actions:
    - "check_setup": CALL THIS FIRST to check if payment method exists
    - "save_email": Save donor email for receipt (call before make_payment if email provided)
    - "make_payment": Process donation (requires amount; ask for email first if not set)

    Args:
        action: "check_setup", "save_email", or "make_payment"
        amount: Amount in CAD (for make_payment only)
        description: Optional description
        user_confirmation: True if user confirmed payment
        donor_email: Donor's email address (for save_email action)
        payment_method: "stripe", "paypal", or "auto" (for make_payment). Defaults to "auto".
    """
    # Get payment context
    ctx = get_payment_context()

    if ctx is None:
        return """Payment system is not available in the current context.
Please try again through the web interface at https://northernontarioparty.org/donate-today/"""

    # Check if at least one payment system is configured
    stripe_configured = stripe_service.is_configured()
    paypal_configured = paypal_service.is_configured()

    if not stripe_configured and not paypal_configured:
        return """No payment systems are configured.
Please donate directly at https://northernontarioparty.org/donate-today/"""

    # Handle different actions
    if action == "check_setup":
        return _check_payment_setup(ctx)
    elif action == "list_methods":
        return _list_payment_methods(ctx)
    elif action == "save_email":
        return _save_donor_email(ctx, donor_email)
    elif action == "make_payment":
        return _make_payment(ctx, amount, description, user_confirmation, payment_method)
    else:
        return f"Unknown action: {action}. Valid actions are: check_setup, save_email, list_methods, make_payment"


def _check_payment_setup(ctx: dict) -> str:
    """Check if the user has payment methods set up (Stripe and/or PayPal)."""
    stripe_setup = ctx.get("payment_setup_complete", False)
    paypal_setup = ctx.get("paypal_setup_complete", False)

    if not stripe_setup and not paypal_setup:
        setup_options = []
        if stripe_service.is_configured():
            setup_options.append('- Click "Setup Card Payment" to add a credit/debit card via Stripe')
        if paypal_service.is_configured():
            setup_options.append('- Click "Setup PayPal" to link your PayPal account')

        return f"""You haven't set up a payment method yet.

To set up your payment method securely:
{chr(10).join(setup_options)}

Your payment information is stored securely - we never see your full card number or PayPal credentials."""

    # Build status message showing all set up methods
    status_parts = []

    if stripe_setup:
        methods = ctx.get("payment_methods", [])
        if methods:
            method = methods[0]
            status_parts.append(f"- Card: {method.get('brand', 'Card').title()} ending in {method.get('last4', '****')}")

    if paypal_setup:
        paypal_email = ctx.get("paypal_payer_email", "linked")
        status_parts.append(f"- PayPal: {paypal_email}")

    result = "You have the following payment methods set up:\n" + "\n".join(status_parts)

    # Suggest adding more if only one is set up
    if stripe_setup and not paypal_setup and paypal_service.is_configured():
        result += '\n\nYou can also link your PayPal account by clicking "Setup PayPal".'
    elif paypal_setup and not stripe_setup and stripe_service.is_configured():
        result += '\n\nYou can also add a card by clicking "Setup Card Payment".'

    result += "\n\nYou're ready to make donations! Just tell me the amount you'd like to donate."

    return result


def _list_payment_methods(ctx: dict) -> str:
    """List the user's saved payment methods (Stripe and PayPal)."""
    stripe_setup = ctx.get("payment_setup_complete", False)
    paypal_setup = ctx.get("paypal_setup_complete", False)

    if not stripe_setup and not paypal_setup:
        return """You don't have any payment methods set up yet.

Click "Setup Card Payment" or "Setup PayPal" to add a payment method."""

    result = "Your saved payment methods:\n\n"
    method_num = 1

    # List Stripe cards
    if stripe_setup:
        methods = ctx.get("payment_methods", [])
        for method in methods:
            brand = method.get("brand", "Card").title()
            last4 = method.get("last4", "****")
            exp = f"{method.get('exp_month', '??')}/{method.get('exp_year', '????')}"
            result += f"{method_num}. {brand} ending in {last4} (expires {exp})\n"
            method_num += 1

    # List PayPal
    if paypal_setup:
        paypal_email = ctx.get("paypal_payer_email", "linked")
        result += f"{method_num}. PayPal ({paypal_email})\n"

    return result


def _save_donor_email(ctx: dict, email: Optional[str]) -> str:
    """Save donor email to session via API."""
    if not email:
        return "Please provide your email address so we can send you a receipt."

    import re
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return "That doesn't look like a valid email address. Please provide a valid email."

    session_id = ctx.get("session_id")
    if session_id:
        import httpx
        try:
            httpx.post(
                "http://localhost:8000/payment/email",
                json={"session_id": session_id, "email": email},
                timeout=5,
            )
        except Exception:
            pass

    # Also update local context so current request benefits immediately
    ctx["donor_email"] = email
    return f"Got it! Receipt will be sent to {email}."


def _make_payment(
    ctx: dict,
    amount: Optional[float],
    description: Optional[str],
    user_confirmation: bool,
    payment_method: Optional[str] = None,
) -> str:
    """Process a payment via Stripe or PayPal."""
    # Validate amount
    if amount is None:
        return "Please specify the amount you'd like to donate."

    if amount <= 0:
        return "The donation amount must be greater than $0."

    # Check spending cap
    spending_cap = config.PAYMENT_SPENDING_CAP
    if amount > spending_cap:
        return f"""The maximum donation amount through this chat is ${spending_cap:.2f} CAD.

For larger donations, please visit https://northernontarioparty.org/donate-today/
or contact the party directly at Northernontarioparty@hotmail.com"""

    # Check available payment methods
    stripe_setup = ctx.get("payment_setup_complete", False)
    paypal_setup = ctx.get("paypal_setup_complete", False)

    if not stripe_setup and not paypal_setup:
        return """You need to set up a payment method before making a donation.

Please click "Setup Card Payment" or "Setup PayPal" to add a payment method."""

    # Determine which payment method to use
    use_stripe = False
    use_paypal = False

    if payment_method == "stripe":
        if not stripe_setup:
            return "Stripe card payment is not set up. Please click 'Setup Card Payment' first."
        use_stripe = True
    elif payment_method == "paypal":
        if not paypal_setup:
            return "PayPal is not set up. Please click 'Setup PayPal' first."
        use_paypal = True
    else:  # auto or None
        # If both are set up, ask user to choose
        if stripe_setup and paypal_setup:
            methods = ctx.get("payment_methods", [])
            card_info = ""
            if methods:
                m = methods[0]
                card_info = f"{m.get('brand', 'Card').title()} ****{m.get('last4', '****')}"
            paypal_email = ctx.get("paypal_payer_email", "linked")

            return f"""You have multiple payment methods. Which would you like to use?

1. Card ({card_info})
2. PayPal ({paypal_email})

Please say "pay with card" or "pay with PayPal"."""
        elif stripe_setup:
            use_stripe = True
        elif paypal_setup:
            use_paypal = True

    # Process the payment with the selected method
    payment_description = description or "Donation to Northern Ontario Party"

    if use_stripe:
        return _make_stripe_payment(ctx, amount, payment_description, user_confirmation)
    elif use_paypal:
        return _make_paypal_payment(ctx, amount, payment_description, user_confirmation)
    else:
        return "No payment method available. Please set up a payment method first."


def _make_stripe_payment(
    ctx: dict,
    amount: float,
    description: str,
    user_confirmation: bool,
) -> str:
    """Process a payment via Stripe."""
    methods = ctx.get("payment_methods", [])
    if not methods:
        return "No card found. Please set up a payment method first."

    primary_method = methods[0]
    customer_id = ctx.get("stripe_customer_id")

    if not customer_id:
        return "Payment session error. Please refresh and try setting up payment again."

    # Check if confirmation is required
    confirmation_threshold = config.PAYMENT_REQUIRE_CONFIRMATION_ABOVE
    if amount > confirmation_threshold and not user_confirmation:
        brand = primary_method.get("brand", "Card").title()
        last4 = primary_method.get("last4", "****")
        return f"""Please confirm your donation:

Amount: ${amount:.2f} CAD
Payment Method: {brand} ending in {last4}
Purpose: {description}

Please confirm by saying "Yes, I confirm the ${amount:.2f} donation" or similar."""

    try:
        result = stripe_service.create_payment_intent(
            customer_id=customer_id,
            payment_method_id=primary_method["id"],
            amount=amount,
            description=description,
            receipt_email=ctx.get("donor_email"),
        )

        if result.get("success"):
            return f"""Thank you! Your donation was successful.

Amount: ${amount:.2f} CAD
Payment Method: Card
Payment ID: {result.get('payment_id', 'N/A')}

Your generous support helps the Northern Ontario Party continue its mission to represent and advocate for Northern Ontario communities. Thank you for being part of this movement!

Is there anything else I can help you with?"""
        else:
            error = result.get("error", "Unknown error")
            return f"""Sorry, the payment could not be processed.

Reason: {error}

Please try again or contact the party directly at Northernontarioparty@hotmail.com for assistance."""

    except Exception as e:
        return f"""An error occurred while processing your payment.

Please try again later or donate directly at https://northernontarioparty.org/donate-today/

Error: {str(e)}"""


def _make_paypal_payment(
    ctx: dict,
    amount: float,
    description: str,
    user_confirmation: bool,
) -> str:
    """Process a payment via PayPal vault."""
    payment_token = ctx.get("paypal_payment_token")
    if not payment_token:
        return "PayPal is not properly set up. Please click 'Setup PayPal' to link your account."

    paypal_email = ctx.get("paypal_payer_email", "your PayPal account")

    # Check if confirmation is required
    confirmation_threshold = config.PAYMENT_REQUIRE_CONFIRMATION_ABOVE
    if amount > confirmation_threshold and not user_confirmation:
        return f"""Please confirm your donation:

Amount: ${amount:.2f} CAD
Payment Method: PayPal ({paypal_email})
Purpose: {description}

Please confirm by saying "Yes, I confirm the ${amount:.2f} donation" or similar."""

    try:
        result = paypal_service.create_order_with_vault(
            payment_token_id=payment_token,
            amount=amount,
            description=description,
        )

        if result.get("success"):
            return f"""Thank you! Your donation was successful.

Amount: ${amount:.2f} CAD
Payment Method: PayPal ({paypal_email})
Order ID: {result.get('order_id', 'N/A')}

Your generous support helps the Northern Ontario Party continue its mission to represent and advocate for Northern Ontario communities. Thank you for being part of this movement!

Is there anything else I can help you with?"""
        else:
            error = result.get("error", "Unknown error")
            return f"""Sorry, the PayPal payment could not be processed.

Reason: {error}

Please try again or contact the party directly at Northernontarioparty@hotmail.com for assistance."""

    except Exception as e:
        return f"""An error occurred while processing your PayPal payment.

Please try again later or donate directly at https://northernontarioparty.org/donate-today/

Error: {str(e)}"""
