"""
common.py
=========
Shared configuration, helpers, and error types used across all tool modules.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

# ----------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------

load_dotenv()  # loads variables from a .env file in the current directory

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent_tools")

# Environment variables / config
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "tavily").lower()

# Sandbox root: all filesystem/shell tools are restricted to this directory
# to prevent path traversal / accidental writes outside the workspace.
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

class ToolError(Exception):
    """Raised when a tool encounters a recoverable error."""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def resolve_path(path: str) -> Path:
    """
    Resolve a user-supplied path against WORKSPACE_DIR and ensure
    it does not escape the sandbox (prevents '../../etc/passwd' style attacks).
    """
    candidate = (WORKSPACE_DIR / path).resolve()
    if not str(candidate).startswith(str(WORKSPACE_DIR)):
        raise ToolError(f"Path '{path}' resolves outside the workspace directory.")
    return candidate


def ok(data: Any = None, message: str = "") -> Dict[str, Any]:
    """Build a standard success response."""
    return {"success": True, "message": message, "data": data}


def err(message: str) -> Dict[str, Any]:
    """Build a standard error response (and log it)."""
    logger.error(message)
    return {"success": False, "message": message, "data": None}