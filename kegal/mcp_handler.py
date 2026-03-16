"""Orchestrator-managed MCP client.

Connects to a single MCP server (stdio or SSE), lists its tools, and
executes tool calls on behalf of the compiler.  The LLM layer never
talks MCP directly — it only sees translated LLMTool definitions and
receives plain-string results back.

The async MCP session runs on a dedicated background thread with its own
event loop so that the synchronous compiler can call connect/call_tool/
disconnect without spawning a new event loop for each call (which would
break anyio's task-group lifetime requirements).
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


class McpHandler:
    def __init__(self, server: GraphMcpServer) -> None:
        self._server = server
        self._session: ClientSession | None = None
        self._exit_stack = None
        self._tools: dict[str, LLMTool] = {}

        # Dedicated event loop running on a background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self):
        self._loop.run_forever()

    def _run(self, coro) -> Any:
        """Submit a coroutine to the background loop and block until done."""
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        self._run(self._aconnect())

    async def _aconnect(self) -> None:
        from contextlib import AsyncExitStack
        self._exit_stack = AsyncExitStack()

        if self._server.transport == "stdio":
            if not self._server.command:
                raise ValueError(f"MCP server '{self._server.id}': 'command' required for stdio")
            params = StdioServerParameters(
                command=self._server.command,
                args=self._server.args or [],
                env=self._server.env,
            )
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        else:
            if not self._server.url:
                raise ValueError(f"MCP server '{self._server.id}': 'url' required for sse")
            read, write = await self._exit_stack.enter_async_context(sse_client(self._server.url))

        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        await self._refresh_tools()
        logger.info(f"MCP server '{self._server.id}' connected — {len(self._tools)} tools available")

    def disconnect(self) -> None:
        if self._exit_stack is not None:
            try:
                self._run(self._adisconnect())
            except Exception as e:
                logger.warning(f"MCP server '{self._server.id}' disconnect error: {e}")
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    async def _adisconnect(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None
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
