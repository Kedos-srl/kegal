from pydantic import BaseModel


class NodeReact(BaseModel):
    max_iterations: int = 10
    compact: bool = False
    compact_threshold: float = 0.8
