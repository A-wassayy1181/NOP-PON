"""FastAPI REST API for the NOP Chatbot."""

from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .agent import NOPChatbot
from .config import config
from .stripe_service import stripe_service
from .paypal_service import paypal_service
from .tools.payment import set_payment_context

# Frontend path
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# Request/Response models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    session_id: Optional[str] = Field(None, description="Optional session ID for conversation continuity")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str = Field(..., description="Chatbot response")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")


class EscalateRequest(BaseModel):
    """Request model for escalation endpoint."""
    reason: str = Field(..., min_length=1, max_length=1000, description="Reason for escalation")
    user_email: Optional[str] = Field(None, description="User email for follow-up")
    user_name: Optional[str] = Field(None, description="User name")
    session_id: Optional[str] = Field(None, description="Session ID to include conversation history")


class EscalateResponse(BaseModel):
    """Response model for escalation endpoint."""
    success: bool = Field(..., description="Whether escalation was successful")
    message: str = Field(..., description="Escalation result message")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str = Field(..., description="Service status")
    llm_provider: str = Field(..., description="Configured LLM provider")
    knowledge_base_ready: bool = Field(..., description="Whether knowledge base is initialized")


class PaymentSetupRequest(BaseModel):
    """Request model for payment setup endpoint."""
    session_id: str = Field(..., description="Session ID for the user")


class PaymentSetupResponse(BaseModel):
    """Response model for payment setup endpoint."""
    checkout_url: str = Field(..., description="Stripe Checkout URL to redirect user to")
    checkout_session_id: str = Field(..., description="Stripe checkout session ID")


class PaymentStatusResponse(BaseModel):
    """Response model for payment status endpoint."""
    # Stripe status
    setup_complete: bool = Field(..., description="Whether Stripe payment is set up")
    payment_methods: list = Field(default=[], description="List of saved Stripe payment methods")
    publishable_key: str = Field(..., description="Stripe publishable key for frontend")
    # PayPal status
    paypal_setup_complete: bool = Field(default=False, description="Whether PayPal is set up")
    paypal_email: Optional[str] = Field(default=None, description="Linked PayPal email")
    paypal_client_id: str = Field(default="", description="PayPal client ID for frontend")


class SessionData:
    """Container for session data including chatbot and payment info."""
    def __init__(self):
        self.chatbot: Optional[NOPChatbot] = None
        # Stripe fields
        self.stripe_customer_id: Optional[str] = None
        self.payment_methods: list = []
        self.payment_setup_complete: bool = False
        self.pending_checkout_session_id: Optional[str] = None
        self.donor_email: Optional[str] = None
        # PayPal fields
        self.paypal_payment_token: Optional[str] = None
        self.paypal_payer_email: Optional[str] = None
        self.paypal_setup_complete: bool = False
        self.pending_paypal_setup_token: Optional[str] = None

    def get_payment_context(self, session_id: str = "") -> dict:
        """Get payment context dict for the payment tool."""
        return {
            # Stripe context
            "stripe_customer_id": self.stripe_customer_id,
            "payment_methods": self.payment_methods,
            "payment_setup_complete": self.payment_setup_complete,
            "donor_email": self.donor_email,
            "session_id": session_id,
            # PayPal context
            "paypal_payment_token": self.paypal_payment_token,
            "paypal_payer_email": self.paypal_payer_email,
            "paypal_setup_complete": self.paypal_setup_complete,
        }


# Session storage for multiple conversations
sessions: dict[str, SessionData] = {}


def get_or_create_session(session_id: Optional[str]) -> tuple[SessionData, str]:
    """Get existing session or create a new one."""
    import uuid

    if session_id and session_id in sessions:
        session_data = sessions[session_id]
        # Ensure chatbot is initialized
        if session_data.chatbot is None:
            session_data.chatbot = NOPChatbot()
            session_data.chatbot.initialize()
        return session_data, session_id

    # Create new session
    new_id = session_id or str(uuid.uuid4())
    session_data = SessionData()
    session_data.chatbot = NOPChatbot()
    session_data.chatbot.initialize()
    sessions[new_id] = session_data

    # Limit sessions to prevent memory issues (simple LRU-like cleanup)
    if len(sessions) > 100:
        # Remove oldest sessions
        oldest_keys = list(sessions.keys())[:50]
        for key in oldest_keys:
            del sessions[key]

    return session_data, new_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup: Initialize default chatbot
    print("Starting NOP Chatbot API...")
    if config.validate():
        default_session = SessionData()
        default_session.chatbot = NOPChatbot()
        default_session.chatbot.initialize()
        sessions["default"] = default_session
        print("Default chatbot session initialized")
    else:
        print("Warning: Configuration not valid. API will initialize on first request.")

    # Check Stripe configuration
    if stripe_service.is_configured():
        print("Stripe payment integration enabled")
    else:
        print("Warning: Stripe not configured. Stripe payments will be disabled.")

    # Check PayPal configuration
    if paypal_service.is_configured():
        print("PayPal payment integration enabled")
    else:
        print("Warning: PayPal not configured. PayPal payments will be disabled.")

    yield
    # Shutdown
    print("Shutting down NOP Chatbot API...")
    sessions.clear()


# Create FastAPI app
app = FastAPI(
    title="NOP Chatbot API",
    description="REST API for the Northern Ontario Party AI Chatbot",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Check the health status of the chatbot service."""
    return HealthResponse(
        status="healthy",
        llm_provider=config.LLM_PROVIDER,
        knowledge_base_ready="default" in sessions,
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """Send a message to the chatbot and receive a response.

    Maintains conversation history within a session for context-aware responses.
    """
    try:
        session_data, session_id = get_or_create_session(request.session_id)

        # Set payment context for the payment tool
        set_payment_context(session_data.get_payment_context(session_id))

        response = session_data.chatbot.chat(request.message)

        return ChatResponse(
            response=response,
            session_id=session_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {str(e)}. Please check API keys.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}",
        )


@app.post("/escalate", response_model=EscalateResponse, tags=["Support"])
async def escalate(request: EscalateRequest):
    """Manually escalate a conversation to a human representative.

    Sends the user's concern and conversation history to the party contact.
    """
    from .tools.escalation import escalation_tool

    try:
        # Get conversation summary if session exists
        conversation_summary = "No prior conversation."
        if request.session_id and request.session_id in sessions:
            session_data = sessions[request.session_id]
            if session_data.chatbot:
                conversation_summary = session_data.chatbot.get_conversation_summary()

        # Call escalation tool
        result = escalation_tool.invoke({
            "reason": request.reason,
            "conversation_summary": conversation_summary,
            "user_email": request.user_email or "",
            "user_name": request.user_name or "",
        })

        return EscalateResponse(
            success=True,
            message=result,
        )
    except Exception as e:
        return EscalateResponse(
            success=False,
            message=f"Escalation failed: {str(e)}. Please contact the party directly at Northernontarioparty@hotmail.com",
        )


@app.post("/clear", tags=["Session"])
async def clear_session(session_id: Optional[str] = None):
    """Clear the conversation history for a session."""
    if session_id and session_id in sessions:
        session_data = sessions[session_id]
        if session_data.chatbot:
            session_data.chatbot.clear_history()
        return {"message": "Session cleared", "session_id": session_id}
    elif session_id:
        return {"message": "Session not found", "session_id": session_id}
    else:
        return {"message": "No session ID provided"}


# Payment endpoints
@app.post("/payment/setup", response_model=PaymentSetupResponse, tags=["Payment"])
async def payment_setup(request: PaymentSetupRequest):
    """Create a Stripe Checkout session for card setup.

    Returns a checkout URL where the user should be redirected to enter card details.
    """
    if not stripe_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Payment system is not configured. Please donate at https://northernontarioparty.org/donate-today/",
        )

    try:
        # Ensure session exists
        session_data, session_id = get_or_create_session(request.session_id)

        # Create Stripe Checkout session
        # Use the API server URL for callbacks
        base_url = "http://localhost:8000"
        result = stripe_service.create_checkout_session(
            success_url=f"{base_url}/payment/setup/complete?session_id={session_id}&checkout_session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/?payment_cancelled=true",
            session_id=session_id,
        )

        # Store the checkout session ID for verification
        session_data.pending_checkout_session_id = result["checkout_session_id"]

        return PaymentSetupResponse(
            checkout_url=result["checkout_url"],
            checkout_session_id=result["checkout_session_id"],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create checkout session: {str(e)}",
        )


@app.get("/payment/setup/complete", tags=["Payment"])
async def payment_setup_complete(session_id: str, checkout_session_id: str):
    """Callback after successful Stripe Checkout.

    Retrieves customer and payment method info and stores in session.
    Redirects back to the chat interface.
    """
    from fastapi.responses import RedirectResponse

    if not stripe_service.is_configured():
        return RedirectResponse(url="/?payment_error=not_configured")

    try:
        # Get or create session
        session_data, session_id = get_or_create_session(session_id)

        # Retrieve customer and payment method from Stripe
        payment_info = stripe_service.get_customer_from_checkout(checkout_session_id)

        # Store in session
        session_data.stripe_customer_id = payment_info["customer_id"]
        session_data.payment_methods = [{
            "id": payment_info["payment_method_id"],
            "brand": payment_info["card_brand"],
            "last4": payment_info["card_last4"],
            "exp_month": payment_info["card_exp_month"],
            "exp_year": payment_info["card_exp_year"],
        }]
        session_data.donor_email = payment_info.get("donor_email")
        session_data.payment_setup_complete = True
        session_data.pending_checkout_session_id = None

        # Redirect back to chat with success message
        return RedirectResponse(url=f"/?payment_success=true&session_id={session_id}")

    except Exception as e:
        import traceback
        print(f"Payment setup complete error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        return RedirectResponse(url=f"/?payment_error={str(e)}")


@app.get("/payment/status", response_model=PaymentStatusResponse, tags=["Payment"])
async def payment_status(session_id: str):
    """Get the payment status for a session."""
    if session_id not in sessions:
        return PaymentStatusResponse(
            setup_complete=False,
            payment_methods=[],
            publishable_key=config.STRIPE_PUBLISHABLE_KEY,
            paypal_setup_complete=False,
            paypal_email=None,
            paypal_client_id=config.PAYPAL_CLIENT_ID,
        )

    session_data = sessions[session_id]
    return PaymentStatusResponse(
        setup_complete=session_data.payment_setup_complete,
        payment_methods=session_data.payment_methods,
        publishable_key=config.STRIPE_PUBLISHABLE_KEY,
        paypal_setup_complete=session_data.paypal_setup_complete,
        paypal_email=session_data.paypal_payer_email,
        paypal_client_id=config.PAYPAL_CLIENT_ID,
    )


class PayPalSetupRequest(BaseModel):
    """Request model for PayPal setup endpoint."""
    session_id: str = Field(..., description="Session ID for the user")


class PayPalSetupResponse(BaseModel):
    """Response model for PayPal setup endpoint."""
    approval_url: str = Field(..., description="PayPal approval URL to redirect user to")
    setup_token_id: str = Field(..., description="PayPal setup token ID")


@app.post("/payment/paypal/setup", response_model=PayPalSetupResponse, tags=["Payment"])
async def paypal_setup(request: PayPalSetupRequest):
    """Create a PayPal vault setup token.

    Returns an approval URL where the user should be redirected to link their PayPal account.
    """
    if not paypal_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="PayPal is not configured. Please donate at https://northernontarioparty.org/donate-today/",
        )

    try:
        # Ensure session exists
        session_data, session_id = get_or_create_session(request.session_id)

        # Create PayPal setup token
        base_url = "http://localhost:8000"
        result = paypal_service.create_setup_token(
            return_url=f"{base_url}/payment/paypal/setup/complete?session_id={session_id}",
            cancel_url=f"{base_url}/?paypal_cancelled=true",
            session_id=session_id,
        )

        # Store the setup token for verification
        session_data.pending_paypal_setup_token = result["setup_token_id"]

        return PayPalSetupResponse(
            approval_url=result["approval_url"],
            setup_token_id=result["setup_token_id"],
        )

    except Exception as e:
        import traceback
        print(f"PayPal setup error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create PayPal setup: {str(e)}",
        )


@app.get("/payment/paypal/setup/complete", tags=["Payment"])
async def paypal_setup_complete(session_id: str):
    """Callback after successful PayPal vault approval.

    Converts the setup token to a payment token and stores it in session.
    Redirects back to the chat interface.
    """
    from fastapi.responses import RedirectResponse

    if not paypal_service.is_configured():
        return RedirectResponse(url="/?paypal_error=not_configured")

    try:
        # Get or create session
        session_data, session_id = get_or_create_session(session_id)

        # Get the pending setup token
        setup_token_id = session_data.pending_paypal_setup_token
        if not setup_token_id:
            return RedirectResponse(url="/?paypal_error=no_setup_token")

        # Convert setup token to payment token
        token_info = paypal_service.create_payment_token(setup_token_id)

        # Store in session
        session_data.paypal_payment_token = token_info["payment_token_id"]
        session_data.paypal_payer_email = token_info.get("payer_email")
        session_data.paypal_setup_complete = True
        session_data.pending_paypal_setup_token = None

        # Redirect back to chat with success message
        return RedirectResponse(url=f"/?paypal_success=true&session_id={session_id}")

    except Exception as e:
        import traceback
        print(f"PayPal setup complete error: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        return RedirectResponse(url=f"/?paypal_error={str(e)}")


class DonorEmailRequest(BaseModel):
    """Request model for saving donor email."""
    session_id: str
    email: str


@app.post("/payment/email", tags=["Payment"])
async def save_donor_email(request: DonorEmailRequest):
    """Save the donor's email to the session for Stripe receipts."""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    sessions[request.session_id].donor_email = request.email
    return {"success": True}


# Serve frontend
@app.get("/", tags=["Frontend"])
async def serve_frontend():
    """Serve the chat frontend."""
    return FileResponse(FRONTEND_DIR / "index.html")


# Run with: uvicorn src.api:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
