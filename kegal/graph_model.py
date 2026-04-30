from pydantic import BaseModel


class GraphModel(BaseModel):
    llm: str
    model: str
    api_key: str | None = None
    host: str | None = None
    context_window: int | None = None
    aws_region_name: str | None = None
    aws_access_key: str | None = None
    aws_secret_key: str | None = None
