from pydantic import BaseModel


class NodeReact(BaseModel):
    max_iterations: int = 10
    resume: bool = False
    resume_threshold: float = 0.8
