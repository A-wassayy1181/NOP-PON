"""Knowledge base module - loads NOP documents directly from text files."""

from pathlib import Path
from typing import Dict, Optional

from .config import config


class KnowledgeBase:
    """Simple knowledge base that loads all documents into memory."""

    def __init__(self):
        self.documents: Dict[str, str] = {}
        self.full_context: str = ""
        self._initialized = False

    def load_documents(self) -> None:
        """Load all text documents from the data directory."""
        data_path = config.DATA_PATH
        if not data_path.exists():
            raise FileNotFoundError(f"Data directory not found: {data_path}")

        self.documents = {}
        for txt_file in sorted(data_path.glob("*.txt")):
            try:
                content = txt_file.read_text(encoding="utf-8")
                self.documents[txt_file.name] = content
            except Exception as e:
                print(f"Warning: Failed to load {txt_file}: {e}")

        # Combine all documents into one context string
        self.full_context = "\n\n".join([
            f"=== {name} ===\n{content}"
            for name, content in self.documents.items()
        ])

        print(f"Loaded {len(self.documents)} documents from {data_path}")

    def initialize(self) -> None:
        """Initialize the knowledge base."""
        if self._initialized:
            return
        self.load_documents()
        self._initialized = True

    def get_context(self) -> str:
        """Get all knowledge base content as a single context string."""
        if not self._initialized:
            self.initialize()
        return self.full_context

    def get_document(self, name: str) -> Optional[str]:
        """Get a specific document by filename."""
        if not self._initialized:
            self.initialize()
        return self.documents.get(name)

    def search(self, query: str) -> str:
        """Simple keyword search - returns all content (LLM will filter)."""
        if not self._initialized:
            self.initialize()
        return self.full_context


# Singleton instance
knowledge_base = KnowledgeBase()
