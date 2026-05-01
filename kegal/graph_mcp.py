from pydantic import BaseModel
from typing import Literal


class GraphMcpServer(BaseModel):
    id: str
    transport: Literal["stdio", "sse"]
    # stdio transport
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    # sse transport
    url: str | None = None
