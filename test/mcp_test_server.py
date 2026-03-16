"""Minimal MCP test server (stdio) — used only by test/test_mcp.py.

Exposes two tools:
  - get_weather(city: str) → str
  - add_numbers(a: int, b: int) → str
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kegal-test-server")


@mcp.tool()
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is sunny and 22°C."


@mcp.tool()
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together."""
    return str(a + b)


if __name__ == "__main__":
    mcp.run(transport="stdio")
