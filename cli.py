#!/usr/bin/env python3
"""Command-line interface for the NOP Chatbot."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agent import NOPChatbot
from src.config import config


WELCOME_MESSAGE = """
================================================================================
         Northern Ontario Party - AI Assistant
================================================================================

Welcome! I'm here to help you with information about the Northern Ontario Party.

I can help you with:
  - Questions about the party, its history, and mission
  - Membership and donation information
  - Contact information and how to get involved
  - Connecting you with a party representative

Commands:
  /quit or /exit  - Exit the chatbot
  /clear          - Clear conversation history
  /escalate       - Request to speak with a human
  /help           - Show this help message

================================================================================
"""

HELP_MESSAGE = """
Available Commands:
  /quit, /exit    - Exit the chatbot
  /clear          - Clear conversation history and start fresh
  /escalate       - Request to speak with a party representative
  /help           - Show this help message

Tips:
  - Ask me anything about the Northern Ontario Party
  - I can help you join the party or make a donation
  - If you need human assistance, just say "I want to speak to someone"
"""


def print_response(text: str) -> None:
    """Print chatbot response with formatting."""
    print(f"\nAssistant: {text}\n")


def handle_escalation(chatbot: NOPChatbot) -> None:
    """Handle manual escalation request."""
    print("\n--- Escalation Request ---")
    print("I'll help connect you with a party representative.")

    user_name = input("Your name (optional, press Enter to skip): ").strip()
    user_email = input("Your email (optional, press Enter to skip): ").strip()
    reason = input("What would you like to discuss? ").strip()

    if not reason:
        print("Escalation cancelled - no reason provided.")
        return

    # Use the escalation tool
    from src.tools.escalation import escalation_tool

    result = escalation_tool.invoke({
        "reason": reason,
        "conversation_summary": chatbot.get_conversation_summary(),
        "user_email": user_email,
        "user_name": user_name,
    })

    print_response(result)


def main():
    """Main CLI loop."""
    print(WELCOME_MESSAGE)

    # Check configuration
    if not config.validate():
        print("ERROR: Configuration is not valid.")
        print("Please check your .env file and ensure API keys are set.")
        print(f"Current LLM provider: {config.LLM_PROVIDER}")
        print("\nCopy .env.example to .env and add your API keys:")
        print("  - For OpenAI: Set OPENAI_API_KEY")
        print("  - For Anthropic: Set ANTHROPIC_API_KEY and LLM_PROVIDER=anthropic")
        sys.exit(1)

    # Initialize chatbot
    print("Initializing chatbot (this may take a moment on first run)...")
    try:
        chatbot = NOPChatbot()
        chatbot.initialize()
    except Exception as e:
        print(f"ERROR: Failed to initialize chatbot: {e}")
        sys.exit(1)

    print("Ready! Type your message or /help for commands.\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ["/quit", "/exit"]:
                print("\nThank you for chatting with us! Goodbye.")
                break

            if user_input.lower() == "/clear":
                chatbot.clear_history()
                print("\nConversation cleared. Starting fresh!\n")
                continue

            if user_input.lower() == "/help":
                print(HELP_MESSAGE)
                continue

            if user_input.lower() == "/escalate":
                handle_escalation(chatbot)
                continue

            # Regular chat
            response = chatbot.chat(user_input)
            print_response(response)

        except KeyboardInterrupt:
            print("\n\nThank you for chatting with us! Goodbye.")
            break
        except EOFError:
            print("\n\nThank you for chatting with us! Goodbye.")
            break
        except Exception as e:
            print(f"\nError: {e}")
            print("Please try again or type /help for assistance.\n")


if __name__ == "__main__":
    main()
