"""Payment tool for processing donations via Stripe."""

from typing import Optional
from contextvars import ContextVar

from langchain_core.tools import tool

from ..config import config
from ..stripe_service import stripe_service


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
    """
    # Get payment context
    ctx = get_payment_context()

    if ctx is None:
        return """Payment system is not available in the current context.
Please try again through the web interface at https://northernontarioparty.org/donate-today/"""

    # Check if Stripe is configured
    if not stripe_service.is_configured():
        return """The payment system is not yet configured.
Please donate directly at https://northernontarioparty.org/donate-today/"""

    # Handle different actions
    if action == "check_setup":
        return _check_payment_setup(ctx)
    elif action == "list_methods":
        return _list_payment_methods(ctx)
    elif action == "save_email":
        return _save_donor_email(ctx, donor_email)
    elif action == "make_payment":
        return _make_payment(ctx, amount, description, user_confirmation)
    else:
        return f"Unknown action: {action}. Valid actions are: check_setup, save_email, list_methods, make_payment"


def _check_payment_setup(ctx: dict) -> str:
    """Check if the user has payment method set up."""
    if not ctx.get("payment_setup_complete"):
        return """You haven't set up a payment method yet.

To set up your payment method securely:
1. Click the "Setup Payment" button in the chat interface
2. You'll be redirected to Stripe's secure checkout page
3. Enter your card details (handled securely by Stripe)
4. Once complete, you'll be redirected back here

Your card information is stored securely with Stripe - we never see your full card number."""

    customer_id = ctx.get("stripe_customer_id")
    methods = ctx.get("payment_methods", [])

    if not methods:
        return """Your payment setup seems incomplete. Please click "Setup Payment" to add a card."""

    method = methods[0]  # Primary method
    return f"""You have a payment method set up:
- Card: {method.get('brand', 'Card').title()} ending in {method.get('last4', '****')}

You're ready to make donations! Just tell me the amount you'd like to donate."""


def _list_payment_methods(ctx: dict) -> str:
    """List the user's saved payment methods."""
    if not ctx.get("payment_setup_complete"):
        return """You don't have any payment methods set up yet.

Click the "Setup Payment" button to securely add a card through Stripe."""

    methods = ctx.get("payment_methods", [])

    if not methods:
        return "No payment methods found. Please click 'Setup Payment' to add one."

    result = "Your saved payment methods:\n\n"
    for i, method in enumerate(methods, 1):
        brand = method.get("brand", "Card").title()
        last4 = method.get("last4", "****")
        exp = f"{method.get('exp_month', '??')}/{method.get('exp_year', '????')}"
        result += f"{i}. {brand} ending in {last4} (expires {exp})\n"

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
) -> str:
    """Process a payment."""
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

    # Check if payment is set up
    if not ctx.get("payment_setup_complete"):
        return """You need to set up a payment method before making a donation.

Please click the "Setup Payment" button to securely add your card through Stripe."""

    # Get payment method
    methods = ctx.get("payment_methods", [])
    if not methods:
        return "No payment method found. Please set up a payment method first."

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
Purpose: {description or 'Donation to Northern Ontario Party'}

Please confirm by saying "Yes, I confirm the ${amount:.2f} donation" or similar."""

    # Process the payment
    payment_description = description or "Donation to Northern Ontario Party"

    try:
        result = stripe_service.create_payment_intent(
            customer_id=customer_id,
            payment_method_id=primary_method["id"],
            amount=amount,
            description=payment_description,
            receipt_email=ctx.get("donor_email"),
        )

        if result.get("success"):
            return f"""Thank you! Your donation was successful.

Amount: ${amount:.2f} CAD
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
