"""
search_tools.py
=================
Web search via Tavily or Serper (configurable through SEARCH_PROVIDER).

Requires SEARCH_API_KEY in .env.
"""

from __future__ import annotations

from typing import Dict, Any

import requests

from .common import ok, err, SEARCH_API_KEY, SEARCH_PROVIDER


def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web using the configured provider (Tavily or Serper).

    Requires SEARCH_API_KEY (and optionally SEARCH_PROVIDER) in .env.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.

    Returns:
        dict with success flag, message, and data (list of {title, url, snippet}).
    """
    if not SEARCH_API_KEY:
        return err("SEARCH_API_KEY is not set in the environment (.env).")

    try:
        if SEARCH_PROVIDER == "tavily":
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": SEARCH_API_KEY,
                    "query": query,
                    "max_results": max_results,
                },
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
            results = [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("content"),
                }
                for r in payload.get("results", [])
            ]

        elif SEARCH_PROVIDER == "serper":
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SEARCH_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": max_results},
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
            results = [
                {
                    "title": r.get("title"),
                    "url": r.get("link"),
                    "snippet": r.get("snippet"),
                }
                for r in payload.get("organic", [])[:max_results]
            ]

        else:
            return err(f"Unknown SEARCH_PROVIDER: '{SEARCH_PROVIDER}' (expected 'tavily' or 'serper')")

        return ok(data={"results": results}, message=f"Found {len(results)} results for query: {query}")

    except requests.RequestException as e:
        return err(f"Web search request failed: {e}")
    except Exception as e:
        return err(f"Web search failed: {e}")