import os
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY not set in .env file")
        _client = TavilyClient(api_key=api_key)
    return _client

def search(query, max_results=5):
    """Search the web for a query. Returns list of results."""
    client = get_client()
    try:
        response = client.search(query, max_results=max_results)
        return response.get("results", [])
    except Exception as e:
        print(f"  ✗ Search failed for '{query}': {e}")
        return []

def extract(urls):
    """Extract full content from a list of URLs."""
    client = get_client()
    try:
        response = client.extract(urls=urls)
        return response.get("results", [])
    except Exception as e:
        print(f"  ✗ Extract failed: {e}")
        return []

def research(query):
    """
    Deep research on a query (uses more credits).
    Returns a markdown report string.
    """
    client = get_client()
    try:
        response = client.research(input=query, model="mini")
        # Research API returns a report field
        return response if isinstance(response, str) else str(response)
    except Exception as e:
        print(f"  ✗ Research failed for '{query}': {e}")
        return None