from pydantic import BaseModel


class ChatHistoryFile(BaseModel):
    path: str
    auto: bool = False
