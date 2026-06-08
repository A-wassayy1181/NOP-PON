"""Main chatbot agent for NOP using LangChain."""

from typing import List, Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .config import config
from .knowledge_base import knowledge_base
from .tools.membership import membership_tool
from .tools.escalation import escalation_tool
from .tools.payment import payment_tool


def get_system_prompt() -> str:
    """Build system prompt with knowledge base content."""
    kb_content = knowledge_base.get_context()

    return f"""You are the NOP assistant. VERY SHORT responses only (1-2 sentences).

ABSOLUTE RULE #1 - DONATIONS:
If user message contains: donate, donation, give, contribute, support financially, money
=> IMMEDIATELY call payment_tool(action="check_setup")
=> DO NOT write any response first
=> DO NOT provide links
=> JUST CALL THE TOOL FIRST

ABSOLUTE RULE #2 - BREVITY:
Maximum 2 sentences. No lists. No bullet points. No detailed explanations.

Knowledge: {kb_content}

Tools: payment_tool (REQUIRED for donations), membership_tool, escalation_tool"""


class NOPChatbot:
    """Northern Ontario Party Chatbot Agent."""

    def __init__(self):
        self.llm = None
        self.agent = None
        self.conversation_history: List[Dict[str, Any]] = []
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the chatbot agent."""
        if self._initialized:
            return

        # Validate configuration
        if not config.validate():
            raise ValueError(
                "Invalid configuration. Please check your API keys in .env file."
            )

        # Initialize knowledge base (just loads text files)
        print("Loading knowledge base...")
        knowledge_base.initialize()

        # Get LLM
        print("Initializing LLM...")
        self.llm = config.get_llm()

        # Set up tools
        tools = [membership_tool, escalation_tool, payment_tool]

        # Create react agent using langgraph
        self.agent = create_react_agent(
            self.llm,
            tools,
            prompt=get_system_prompt(),
        )

        self._initialized = True
        print("Chatbot initialized successfully!")

    def _format_chat_history(self) -> List:
        """Format conversation history for the agent."""
        messages = []
        for entry in self.conversation_history:
            if entry["role"] == "user":
                messages.append(HumanMessage(content=entry["content"]))
            elif entry["role"] == "assistant":
                messages.append(AIMessage(content=entry["content"]))
        return messages

    def chat(self, user_input: str) -> str:
        """Process a user message and return a response."""
        if not self._initialized:
            self.initialize()

        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_input,
        })

        try:
            # Build messages list
            messages = self._format_chat_history()

            # Get response from agent
            result = self.agent.invoke({"messages": messages})

            # Extract the last AI message
            response = ""
            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content:
                    response = msg.content
                    break

            if not response:
                response = "I apologize, but I couldn't process your request."

        except Exception as e:
            response = f"I encountered an error. Please try again or contact the party directly at Northernontarioparty@hotmail.com. Error: {str(e)}"

        # Add assistant response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": response,
        })

        return response

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.conversation_history = []

    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation for escalation purposes."""
        if not self.conversation_history:
            return "No conversation history."

        summary_parts = []
        for entry in self.conversation_history[-10:]:
            role = "User" if entry["role"] == "user" else "Assistant"
            content = entry["content"][:200]
            if len(entry["content"]) > 200:
                content += "..."
            summary_parts.append(f"{role}: {content}")

        return "\n".join(summary_parts)


# Singleton instance
chatbot = NOPChatbot()


def get_chatbot() -> NOPChatbot:
    """Get the chatbot instance, initializing if necessary."""
    if not chatbot._initialized:
        chatbot.initialize()
    return chatbot
