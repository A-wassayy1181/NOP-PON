"""Stripe service layer for payment processing."""

from typing import Optional
import stripe

from .config import config


class StripeService:
    """Encapsulates all Stripe payment operations."""

    def __init__(self):
        """Initialize Stripe with API key."""
        if config.STRIPE_SECRET_KEY:
            stripe.api_key = config.STRIPE_SECRET_KEY

    def is_configured(self) -> bool:
        """Check if Stripe is properly configured."""
        return bool(config.STRIPE_SECRET_KEY and config.STRIPE_PUBLISHABLE_KEY)

    def create_checkout_session(
        self,
        success_url: str,
        cancel_url: str,
        session_id: str,
    ) -> dict:
        """
        Create a Stripe Checkout session for card setup.

        Args:
            success_url: URL to redirect on successful setup
            cancel_url: URL to redirect on cancellation
            session_id: Our internal session ID to track the user

        Returns:
            dict with checkout_url and checkout_session_id
        """
        if not self.is_configured():
            raise ValueError("Stripe is not configured. Please set STRIPE_SECRET_KEY.")

        checkout_session = stripe.checkout.Session.create(
            mode="setup",
            payment_method_types=["card"],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"internal_session_id": session_id},
        )

        return {
            "checkout_url": checkout_session.url,
            "checkout_session_id": checkout_session.id,
        }

    def get_customer_from_checkout(self, checkout_session_id: str) -> dict:
        """
        Retrieve customer and payment method from completed checkout session.

        Args:
            checkout_session_id: The Stripe checkout session ID

        Returns:
            dict with customer_id, payment_method_id, and card details
        """
        if not self.is_configured():
            raise ValueError("Stripe is not configured.")

        print(f"DEBUG: Retrieving checkout session: {checkout_session_id}")

        # Retrieve the checkout session
        checkout_session = stripe.checkout.Session.retrieve(checkout_session_id)
        print(f"DEBUG: Checkout session retrieved, status: {checkout_session.status}")
        print(f"DEBUG: Checkout session type: {type(checkout_session)}")

        if checkout_session.status != "complete":
            raise ValueError("Checkout session is not complete.")

        # Get setup intent ID and retrieve it separately with payment method expanded
        setup_intent_id = checkout_session["setup_intent"]
        if not setup_intent_id:
            raise ValueError("No setup intent found in checkout session.")

        setup_intent = stripe.SetupIntent.retrieve(
            setup_intent_id,
            expand=["payment_method"],
        )

        payment_method = setup_intent["payment_method"]
        if not payment_method:
            raise ValueError("No payment method found in setup intent.")

        # Handle case where payment_method is a string ID instead of object
        if isinstance(payment_method, str):
            payment_method = stripe.PaymentMethod.retrieve(payment_method)

        customer_id = checkout_session.customer
        print(f"DEBUG: customer_id = {customer_id}, type = {type(customer_id)}")

        # If no customer was created, create one now
        if customer_id is None or customer_id == "":
            print("DEBUG: Creating new customer...")
            customer = stripe.Customer.create()
            customer_id = customer.id
            print(f"DEBUG: Created customer: {customer_id}")

            # Attach the payment method to the customer
            pm_id = payment_method.id if hasattr(payment_method, 'id') else payment_method["id"]
            print(f"DEBUG: Attaching payment method {pm_id} to customer {customer_id}")
            stripe.PaymentMethod.attach(pm_id, customer=customer_id)

        # Get card details
        print(f"DEBUG: Getting card details from payment_method type: {type(payment_method)}")
        card = payment_method.card if hasattr(payment_method, 'card') else payment_method["card"]
        pm_id = payment_method.id if hasattr(payment_method, 'id') else payment_method["id"]
        card_brand = card.brand if hasattr(card, 'brand') else card["brand"]
        card_last4 = card.last4 if hasattr(card, 'last4') else card["last4"]
        card_exp_month = card.exp_month if hasattr(card, 'exp_month') else card["exp_month"]
        card_exp_year = card.exp_year if hasattr(card, 'exp_year') else card["exp_year"]

        # Grab email from checkout session (user entered it during Stripe Checkout)
        donor_email = None
        try:
            customer_details = checkout_session.customer_details
            if customer_details:
                donor_email = customer_details.email
        except Exception:
            pass

        print(f"DEBUG: Returning payment info - card: {card_brand} ****{card_last4}")
        return {
            "customer_id": customer_id,
            "payment_method_id": pm_id,
            "card_brand": card_brand,
            "card_last4": card_last4,
            "card_exp_month": card_exp_month,
            "card_exp_year": card_exp_year,
            "donor_email": donor_email,
        }

    def get_customer_payment_methods(self, customer_id: str) -> list:
        """
        List saved payment methods for a customer.

        Args:
            customer_id: The Stripe customer ID

        Returns:
            List of payment methods with card details
        """
        if not self.is_configured():
            raise ValueError("Stripe is not configured.")

        payment_methods = stripe.PaymentMethod.list(
            customer=customer_id,
            type="card",
        )

        methods = []
        for pm in payment_methods.data:
            methods.append({
                "id": pm.id,
                "brand": pm.card.brand,
                "last4": pm.card.last4,
                "exp_month": pm.card.exp_month,
                "exp_year": pm.card.exp_year,
            })

        return methods

    def create_payment_intent(
        self,
        customer_id: str,
        payment_method_id: str,
        amount: float,
        description: str,
        currency: str = "cad",
        receipt_email: Optional[str] = None,
    ) -> dict:
        """
        Create and confirm a PaymentIntent.

        Args:
            customer_id: The Stripe customer ID
            payment_method_id: The payment method to charge
            amount: Amount in dollars (will be converted to cents)
            description: Description for the payment
            currency: Currency code (default: cad)

        Returns:
            dict with payment result (success, payment_id, error if any)
        """
        if not self.is_configured():
            raise ValueError("Stripe is not configured.")

        # Convert dollars to cents
        amount_cents = int(amount * 100)

        try:
            create_kwargs = dict(
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                confirm=True,
                description=description,
                automatic_payment_methods={
                    "enabled": True,
                    "allow_redirects": "never",
                },
                metadata={"description": description},
            )
            if receipt_email:
                create_kwargs["receipt_email"] = receipt_email

            payment_intent = stripe.PaymentIntent.create(**create_kwargs)

            if payment_intent.status == "succeeded":
                return {
                    "success": True,
                    "payment_id": payment_intent.id,
                    "amount": amount,
                    "currency": currency.upper(),
                    "status": payment_intent.status,
                }
            else:
                return {
                    "success": False,
                    "payment_id": payment_intent.id,
                    "status": payment_intent.status,
                    "error": f"Payment status: {payment_intent.status}",
                }

        except stripe.CardError as e:
            return {
                "success": False,
                "error": e.user_message or str(e),
                "error_code": e.code,
            }
        except stripe.StripeError as e:
            return {
                "success": False,
                "error": str(e),
            }


# Singleton instance
stripe_service = StripeService()
