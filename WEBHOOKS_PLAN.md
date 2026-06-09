# Stripe Webhooks — Post-MVP Implementation Plan

## Why Webhooks

The current MVP payment flow is synchronous: `PaymentIntent` with `confirm=True` returns
success/failure instantly in the same chat request. No webhook needed for that.

After MVP, webhooks are required for:
- Party owner gets notified on every donation
- Donor records are stored in a database
- Failed/disputed payments are handled automatically
- Full audit trail for accounting and compliance

---

## Events to Listen For

| Event | What it means | Action |
|---|---|---|
| `payment_intent.succeeded` | Donation confirmed | Save to DB, notify owner, send donor receipt |
| `payment_intent.payment_failed` | Card declined / insufficient funds | Alert donor in chat or via email |
| `payment_intent.canceled` | Payment cancelled | Log it |
| `charge.dispute.created` | Donor disputed a charge | Alert owner immediately |
| `charge.refunded` | Refund issued | Update donor record |
| `customer.deleted` | Customer removed from Stripe | Clean up session data |

---

## Implementation Steps

### 1. Register the webhook in Stripe Dashboard
- Go to Stripe Dashboard → Developers → Webhooks → Add endpoint
- URL: `https://yourdomain.com/webhooks/stripe`
- Select events: all events listed in the table above
- Copy the **Webhook Signing Secret** (`whsec_...`)

### 2. Add env variable
```
STRIPE_WEBHOOK_SECRET=whsec_...
```

Add to `src/config.py`:
```python
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
```

### 3. Add webhook endpoint in `src/api.py`
```python
from fastapi import Request

@app.post("/webhooks/stripe", tags=["Webhooks"])
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET
        )
    except stripe.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    await handle_stripe_event(event)
    return {"received": True}
```

### 4. Add event handler in `src/stripe_service.py`
```python
async def handle_stripe_event(event: dict):
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "payment_intent.succeeded":
        await on_payment_succeeded(data)
    elif event_type == "payment_intent.payment_failed":
        await on_payment_failed(data)
    elif event_type == "charge.dispute.created":
        await on_dispute_created(data)
    elif event_type == "charge.refunded":
        await on_refund(data)
```

### 5. Owner notification on every donation
Send an email to `Northernontarioparty@hotmail.com` on `payment_intent.succeeded`:
```python
async def on_payment_succeeded(payment_intent: dict):
    amount = payment_intent["amount"] / 100
    currency = payment_intent["currency"].upper()
    donor_email = payment_intent.get("receipt_email", "Unknown")
    payment_id = payment_intent["id"]

    # Send owner notification (use SendGrid or smtplib)
    send_email(
        to="Northernontarioparty@hotmail.com",
        subject=f"New Donation: ${amount:.2f} {currency}",
        body=f"""
        A new donation has been received.

        Amount: ${amount:.2f} {currency}
        Donor Email: {donor_email}
        Payment ID: {payment_id}
        Stripe Dashboard: https://dashboard.stripe.com/payments/{payment_id}
        """
    )
```

### 6. Donor database (SQLite to start, Postgres for production)
```python
# models.py (Pydantic + SQLAlchemy)
class Donation(BaseModel):
    payment_id: str
    customer_id: str
    donor_email: str
    amount: float
    currency: str
    status: str  # succeeded / failed / refunded / disputed
    created_at: datetime
```

Save on `payment_intent.succeeded`, update on refund/dispute events.

---

## Email Options (pick one)

| Option | Pros | Cons |
|---|---|---|
| **SendGrid** | Easy API, free tier (100/day) | External dependency |
| **smtplib** (Gmail SMTP) | No extra service | Gmail limits, less reliable |
| **Resend** | Modern API, generous free tier | Newer service |

Recommended: **SendGrid** — straightforward to integrate with FastAPI.

---

## Testing Webhooks Locally

Use the Stripe CLI to forward events to your local server:
```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Trigger a test event:
```bash
stripe trigger payment_intent.succeeded
```

---

## Security Notes

- Always verify the webhook signature using `stripe.Webhook.construct_event` — never skip this
- Store `STRIPE_WEBHOOK_SECRET` in `.env`, never hardcode it
- Return `200 OK` quickly; do heavy processing in a background task to avoid Stripe timeouts
- Stripe retries failed webhook deliveries for up to 3 days

---

## Files to Create/Modify

| File | Change |
|---|---|
| `src/api.py` | Add `/webhooks/stripe` endpoint |
| `src/stripe_service.py` | Add `handle_stripe_event` and sub-handlers |
| `src/config.py` | Add `STRIPE_WEBHOOK_SECRET` |
| `src/email_service.py` | New file — owner + donor email sending |
| `src/models.py` | New file — `Donation` database model |
| `.env` | Add `STRIPE_WEBHOOK_SECRET` |
</content>
