"""PayPal service layer for payment processing using PayPal Vault."""

from typing import Optional
import json

from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment, LiveEnvironment
from paypalcheckoutsdk.orders import OrdersCreateRequest, OrdersCaptureRequest
from paypalhttp import HttpError
import httpx

from .config import config


class PayPalService:
    """Encapsulates all PayPal payment operations including vaulting."""

    def __init__(self):
        """Initialize PayPal client."""
        self._client: Optional[PayPalHttpClient] = None
        if self.is_configured():
            self._init_client()

    def _init_client(self):
        """Initialize the PayPal HTTP client."""
        if config.PAYPAL_MODE == "live":
            environment = LiveEnvironment(
                client_id=config.PAYPAL_CLIENT_ID,
                client_secret=config.PAYPAL_CLIENT_SECRET,
            )
        else:
            environment = SandboxEnvironment(
                client_id=config.PAYPAL_CLIENT_ID,
                client_secret=config.PAYPAL_CLIENT_SECRET,
            )
        self._client = PayPalHttpClient(environment)

    def is_configured(self) -> bool:
        """Check if PayPal is properly configured."""
        return bool(config.PAYPAL_CLIENT_ID and config.PAYPAL_CLIENT_SECRET)

    def _get_access_token(self) -> str:
        """Get OAuth access token for PayPal API calls."""
        if not self.is_configured():
            raise ValueError("PayPal is not configured.")

        base_url = (
            "https://api-m.paypal.com"
            if config.PAYPAL_MODE == "live"
            else "https://api-m.sandbox.paypal.com"
        )

        response = httpx.post(
            f"{base_url}/v1/oauth2/token",
            auth=(config.PAYPAL_CLIENT_ID, config.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _get_base_url(self) -> str:
        """Get PayPal API base URL."""
        return (
            "https://api-m.paypal.com"
            if config.PAYPAL_MODE == "live"
            else "https://api-m.sandbox.paypal.com"
        )

    def create_setup_token(
        self,
        return_url: str,
        cancel_url: str,
        session_id: str,
    ) -> dict:
        """
        Create a PayPal vault setup token to save user's PayPal account.

        Args:
            return_url: URL to redirect on successful setup
            cancel_url: URL to redirect on cancellation
            session_id: Internal session ID to track the user

        Returns:
            dict with setup_token_id and approval_url
        """
        if not self.is_configured():
            raise ValueError("PayPal is not configured.")

        access_token = self._get_access_token()
        base_url = self._get_base_url()

        # Create setup token for PayPal vault
        payload = {
            "payment_source": {
                "paypal": {
                    "description": "Northern Ontario Party Donations",
                    "usage_type": "MERCHANT",
                    "customer_type": "CONSUMER",
                    "experience_context": {
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "CONTINUE",
                        "brand_name": "Northern Ontario Party",
                    },
                }
            },
            "metadata": {
                "internal_session_id": session_id,
            },
        }

        response = httpx.post(
            f"{base_url}/v3/vault/setup-tokens",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": f"setup-{session_id}",
            },
            json=payload,
        )

        print(f"DEBUG PayPal create_setup_token response: {response.status_code}")
        print(f"DEBUG PayPal response body: {response.text}")

        response.raise_for_status()
        data = response.json()

        # Find approval URL in links
        approval_url = None
        for link in data.get("links", []):
            if link.get("rel") == "approve":
                approval_url = link.get("href")
                break

        if not approval_url:
            raise ValueError("No approval URL in PayPal response")

        return {
            "setup_token_id": data.get("id"),
            "approval_url": approval_url,
        }

    def create_payment_token(self, setup_token_id: str) -> dict:
        """
        Convert an approved setup token to a reusable payment token.

        Args:
            setup_token_id: The approved setup token ID

        Returns:
            dict with payment_token_id and payer info
        """
        if not self.is_configured():
            raise ValueError("PayPal is not configured.")

        access_token = self._get_access_token()
        base_url = self._get_base_url()

        payload = {
            "payment_source": {
                "token": {
                    "id": setup_token_id,
                    "type": "SETUP_TOKEN",
                }
            }
        }

        response = httpx.post(
            f"{base_url}/v3/vault/payment-tokens",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        print(f"DEBUG PayPal create_payment_token response: {response.status_code}")
        print(f"DEBUG PayPal response body: {response.text}")

        response.raise_for_status()
        data = response.json()

        # Extract payer email from the response
        payer_email = None
        paypal_source = data.get("payment_source", {}).get("paypal", {})
        payer_email = paypal_source.get("email_address")

        return {
            "payment_token_id": data.get("id"),
            "payer_email": payer_email,
            "customer_id": data.get("customer", {}).get("id"),
        }

    def create_order_with_vault(
        self,
        payment_token_id: str,
        amount: float,
        description: str,
        currency: str = "CAD",
    ) -> dict:
        """
        Create and capture an order using a vaulted payment token.

        Args:
            payment_token_id: The vaulted payment token ID
            amount: Amount to charge
            description: Description of the payment
            currency: Currency code (default: CAD)

        Returns:
            dict with order_id and status
        """
        if not self.is_configured():
            raise ValueError("PayPal is not configured.")

        access_token = self._get_access_token()
        base_url = self._get_base_url()

        # Format amount as string with 2 decimal places
        amount_str = f"{amount:.2f}"

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency,
                        "value": amount_str,
                    },
                    "description": description,
                }
            ],
            "payment_source": {
                "paypal": {
                    "vault_id": payment_token_id,
                }
            },
        }

        response = httpx.post(
            f"{base_url}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        print(f"DEBUG PayPal create_order response: {response.status_code}")
        print(f"DEBUG PayPal response body: {response.text}")

        response.raise_for_status()
        data = response.json()

        order_id = data.get("id")
        status = data.get("status")

        # If order is created but not captured, capture it
        if status == "CREATED" or status == "APPROVED":
            return self.capture_order(order_id)

        # If already captured (shouldn't happen but handle it)
        if status == "COMPLETED":
            return {
                "success": True,
                "order_id": order_id,
                "status": status,
                "amount": amount,
                "currency": currency,
            }

        return {
            "success": False,
            "order_id": order_id,
            "status": status,
            "error": f"Unexpected order status: {status}",
        }

    def capture_order(self, order_id: str) -> dict:
        """
        Capture a PayPal order.

        Args:
            order_id: The PayPal order ID to capture

        Returns:
            dict with capture result
        """
        if not self.is_configured():
            raise ValueError("PayPal is not configured.")

        access_token = self._get_access_token()
        base_url = self._get_base_url()

        response = httpx.post(
            f"{base_url}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )

        print(f"DEBUG PayPal capture_order response: {response.status_code}")
        print(f"DEBUG PayPal response body: {response.text}")

        response.raise_for_status()
        data = response.json()

        status = data.get("status")

        if status == "COMPLETED":
            # Extract capture details
            captures = (
                data.get("purchase_units", [{}])[0]
                .get("payments", {})
                .get("captures", [])
            )
            capture_id = captures[0].get("id") if captures else None
            amount_data = captures[0].get("amount", {}) if captures else {}

            return {
                "success": True,
                "order_id": order_id,
                "capture_id": capture_id,
                "status": status,
                "amount": float(amount_data.get("value", 0)),
                "currency": amount_data.get("currency_code", "CAD"),
            }

        return {
            "success": False,
            "order_id": order_id,
            "status": status,
            "error": f"Capture failed with status: {status}",
        }


# Singleton instance
paypal_service = PayPalService()
