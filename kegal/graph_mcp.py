import re
from pydantic import BaseModel, field_validator
from typing import Literal

# Characters that have special meaning in shells — reject them in the command name
# to prevent accidental or malicious command injection via a crafted YAML config.
_SHELL_SPECIAL = re.compile(r'[;&|`$<>(){}\[\]\n\r\t\\\'"]')


class GraphMcpServer(BaseModel):
    id: str
    transport: Literal["stdio", "sse"]
    # stdio transport
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    # sse transport
    url: str | None = None

    @field_validator("command")
    @classmethod
    def _validate_command(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("MCP server 'command' must not be empty")
        if _SHELL_SPECIAL.search(v):
            raise ValueError(
                f"MCP server 'command' contains shell-special characters: {v!r}. "
                f"Pass arguments via 'args', not embedded in 'command'."
            )
        return v
