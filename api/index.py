"""Vercel serverless function entry point."""

import sys
from pathlib import Path

# Add project root to path so imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api import app

# Vercel expects the app to be named 'app' or 'handler'
# FastAPI apps work directly with Vercel's Python runtime
