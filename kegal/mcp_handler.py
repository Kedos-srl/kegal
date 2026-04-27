"""Orchestrator-managed MCP client.

Connects to a single MCP server (stdio or SSE), lists its tools, and
executes tool calls on behalf of the compiler.  The LLM layer never
talks MCP directly — it only sees translated LLMTool definitions and
receives plain-string results back.

The async MCP session runs on a dedicated background thread with its own
event loop.  The entire session lifetime — connect, tool calls, disconnect —
executes within a single async task so that anyio cancel scopes are always
entered and exited from the same task, avoiding the
"Attempted to exit cancel scope in a different task" error.
"""

import asyncio
import json
import logging
import threading
from concurrent.futures import Future
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from .graph import GraphMcpServer
from .llm.llm_model import LLMTool, LLMStructuredSchema

logger = logging.getLogger(__name__)


_DEFAULT_CALL_TIMEOUT = 60  # seconds per tool call


class McpHandler:
    def __init__(self, server: GraphMcpServer, call_timeout: float = _DEFAULT_CALL_TIMEOUT) -> None:
        self._server = server
        self._call_timeout = call_timeout
        self._session: ClientSession | None = None
        self._tools: dict[str, LLMTool] = {}

        # threading.Event: set once the session is ready (or failed)
        self._ready = threading.Event()
        self._connect_error: Exception | None = None

        # asyncio.Event: set by disconnect() to trigger session teardown
        self._stop_event: asyncio.Event | None = None

        # Dedicated event loop running on a background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Background thread — runs the entire session lifetime in one task
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        self._loop.run_until_complete(self._session_lifetime())

    async def _session_lifetime(self) -> None:
        """Single long-lived coroutine: connect → wait for stop → disconnect."""
        self._stop_event = asyncio.Event()
        try:
            if self._server.transport == "stdio":
                if not self._server.command:
                    raise ValueError(f"MCP server '{self._server.id}': 'command' required for stdio")
                params = StdioServerParameters(
                    command=self._server.command,
                    args=self._server.args or [],
                    env=self._server.env,
                )
                transport_cm = stdio_client(params)
            else:
                if not self._server.url:
                    raise ValueError(f"MCP server '{self._server.id}': 'url' required for sse")
                transport_cm = sse_client(self._server.url)

            async with transport_cm as (read, write):
                async with ClientSession(read, write) as session:
                    self._session = session
                    await session.initialize()
                    await self._refresh_tools()
                    logger.info(
                        f"MCP server '{self._server.id}' connected — "
                        f"{len(self._tools)} tools available"
                    )
                    self._ready.set()
                    # Hold the session open until disconnect() signals us
                    await self._stop_event.wait()

        except Exception as e:
            self._connect_error = e
            self._ready.set()
        finally:
            self._session = None

    def _run(self, coro) -> Any:
        """Submit a coroutine to the background loop and block until done."""
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self._call_timeout)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Block until the session is ready (or raise on failure)."""
        self._ready.wait(timeout=30)
        if self._connect_error is not None:
            raise self._connect_error
        logger.info(f"MCP server '{self._server.id}' ready")

    def disconnect(self) -> None:
        """Signal the session to shut down and wait for the thread to exit."""
        if self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        self._thread.join(timeout=5)
        self._loop.close()
        logger.info(f"MCP server '{self._server.id}' disconnected")

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    async def _refresh_tools(self) -> None:
        result = await self._session.list_tools()
        self._tools = {}
        for tool in result.tools:
            self._tools[tool.name] = self._translate_tool(tool)

    @staticmethod
    def _translate_tool(mcp_tool) -> LLMTool:
        raw_schema = mcp_tool.inputSchema or {}
        raw_props = raw_schema.get("properties", {})
        required = raw_schema.get("required", [])

        parameters: dict[str, LLMStructuredSchema] = {}
        for prop_name, prop_schema in raw_props.items():
            parameters[prop_name] = LLMStructuredSchema(
                type=prop_schema.get("type", "string"),
                description=prop_schema.get("description", ""),
            )

        return LLMTool(
            name=mcp_tool.name,
            description=mcp_tool.description or "",
            parameters=parameters,
            required=required,
        )

    def list_tools(self) -> list[LLMTool]:
        return list(self._tools.values())

    def tool_names(self) -> set[str]:
        return set(self._tools.keys())

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return self._run(self._acall_tool(name, arguments))

    async def _acall_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            raise RuntimeError(f"MCP server '{self._server.id}' is not connected")
        result = await self._session.call_tool(name, arguments)
        parts: list[str] = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(json.dumps(block.model_dump() if hasattr(block, "model_dump") else str(block)))
        return "\n".join(parts)
