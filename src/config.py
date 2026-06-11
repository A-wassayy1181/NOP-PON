"""Configuration module for NOP Chatbot."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # LLM Provider settings (openai, anthropic, or openrouter)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openrouter")

    # OpenRouter settings
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # OpenAI settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Anthropic settings
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    # Email settings for escalation
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    ESCALATION_EMAIL: str = os.getenv(
        "ESCALATION_EMAIL", "Northernontarioparty@hotmail.com"
    )

    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_PATH: Path = Path(os.getenv("DATA_PATH", BASE_DIR / "clean_data"))

    # Stripe Configuration
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

    # PayPal Configuration
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_MODE: str = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live

    # Payment Guardrails (CAD)
    PAYMENT_SPENDING_CAP: float = float(os.getenv("PAYMENT_SPENDING_CAP", "100.00"))
    PAYMENT_REQUIRE_CONFIRMATION_ABOVE: float = float(
        os.getenv("PAYMENT_REQUIRE_CONFIRMATION_ABOVE", "50.00")
    )

    @classmethod
    def get_llm(cls):
        """Get configured LLM instance based on provider setting."""
        provider = cls.LLM_PROVIDER.lower()

        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            if not cls.ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY is required when using Anthropic")
            return ChatAnthropic(
                model=cls.ANTHROPIC_MODEL,
                api_key=cls.ANTHROPIC_API_KEY,
                temperature=0.7,
            )
        elif provider == "openrouter":
            from langchain_openai import ChatOpenAI

            if not cls.OPENROUTER_API_KEY:
                raise ValueError("OPENROUTER_API_KEY is required when using OpenRouter")
            return ChatOpenAI(
                model=cls.OPENROUTER_MODEL,
                api_key=cls.OPENROUTER_API_KEY,
                base_url=cls.OPENROUTER_BASE_URL,
                temperature=0.7,
            )
        else:  # openai
            from langchain_openai import ChatOpenAI

            if not cls.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when using OpenAI")
            return ChatOpenAI(
                model=cls.OPENAI_MODEL,
                api_key=cls.OPENAI_API_KEY,
                temperature=0.7,
            )

    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        provider = cls.LLM_PROVIDER.lower()

        if provider == "anthropic":
            return bool(cls.ANTHROPIC_API_KEY)
        elif provider == "openrouter":
            return bool(cls.OPENROUTER_API_KEY)
        else:  # openai
            return bool(cls.OPENAI_API_KEY)


# Create singleton config instance
config = Config()
