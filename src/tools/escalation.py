"""Human escalation tool for connecting users with party representatives."""

import asyncio
from typing import Optional

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from langchain_core.tools import tool

from ..config import config


async def send_escalation_email(
    user_query: str,
    conversation_summary: str,
    user_email: Optional[str] = None,
    user_name: Optional[str] = None,
) -> bool:
    """Send an escalation email to the party contact."""
    try:
        msg = MIMEMultipart()
        msg["From"] = config.SMTP_USER
        msg["To"] = config.ESCALATION_EMAIL
        msg["Subject"] = "NOP Chatbot - Human Assistance Requested"

        body = f"""A user has requested to speak with a party representative.

User Information:
- Name: {user_name or 'Not provided'}
- Email: {user_email or 'Not provided'}

User's Question/Request:
{user_query}

Conversation Summary:
{conversation_summary}

---
This email was sent automatically by the NOP Chatbot.
Please respond to the user at your earliest convenience.
"""
        msg.attach(MIMEText(body, "plain"))

        await aiosmtplib.send(
            msg,
            hostname=config.SMTP_HOST,
            port=config.SMTP_PORT,
            username=config.SMTP_USER,
            password=config.SMTP_PASSWORD,
            start_tls=True,
        )
        return True

    except Exception as e:
        print(f"Failed to send escalation email: {e}")
        return False


def _send_email_sync(
    user_query: str,
    conversation_summary: str,
    user_email: Optional[str] = None,
    user_name: Optional[str] = None,
) -> bool:
    """Synchronous wrapper for sending escalation email."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        send_escalation_email(user_query, conversation_summary, user_email, user_name)
    )


@tool
def escalation_tool(
    reason: str,
    conversation_summary: str,
    user_email: str = "",
    user_name: str = "",
) -> str:
    """Escalate the conversation to a human party representative.

    Use this tool when:
    - The user explicitly asks to speak with a person/human/representative
    - The user has a complex issue that cannot be resolved by the chatbot
    - The user is frustrated and needs human assistance
    - The question requires official party response
    - The user wants to discuss sensitive or detailed matters

    Args:
        reason: The reason for escalation or the user's specific request
        conversation_summary: A brief summary of the conversation so far
        user_email: Optional user email for follow-up (if provided)
        user_name: Optional user name (if provided)

    Returns:
        Confirmation message about the escalation
    """
    # Check if email is configured
    if not config.SMTP_USER or not config.SMTP_PASSWORD:
        # Email not configured - provide manual contact info
        return f"""I understand you'd like to speak with someone from the party directly.

While I cannot automatically escalate your request at this time, you can reach the Northern Ontario Party through:

**Email:** Northernontarioparty@hotmail.com

**Contact Page:** https://northernontarioparty.org/contact/

Your concern: {reason}

Please reach out to them directly and mention this conversation. They will be happy to assist you personally."""

    # Try to send escalation email
    email_sent = _send_email_sync(
        user_query=reason,
        conversation_summary=conversation_summary,
        user_email=user_email if user_email else None,
        user_name=user_name if user_name else None,
    )

    if email_sent:
        response = """Your request has been escalated to a party representative.

What happens next:
- A team member will review your request
- They will respond as soon as possible"""

        if user_email:
            response += f"\n- They will contact you at: {user_email}"
        else:
            response += """
- Since no email was provided, please check back or contact the party directly at:
  Email: Northernontarioparty@hotmail.com
  Web: https://northernontarioparty.org/contact/"""

        response += "\n\nThank you for your patience. Is there anything else I can help you with in the meantime?"
        return response
    else:
        return f"""I attempted to escalate your request but encountered a technical issue.

Please contact the Northern Ontario Party directly:

**Email:** Northernontarioparty@hotmail.com

**Contact Page:** https://northernontarioparty.org/contact/

Your concern: {reason}

I apologize for the inconvenience. The party team will be happy to assist you."""
