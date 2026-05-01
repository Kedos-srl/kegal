from pydantic import BaseModel, ConfigDict, Field, model_validator


class BlackboardEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    file: str
    cleanup: bool = True
    imports: list[str] = Field(default_factory=list, alias="import")


class GraphBlackboard(BaseModel):
    path: str
    boards: list[BlackboardEntry]

    @model_validator(mode="after")
    def _validate_board_ids(self) -> "GraphBlackboard":
        seen: set[str] = set()
        for entry in self.boards:
            if entry.id in seen:
                raise ValueError(f"Duplicate board id: '{entry.id}'")
            seen.add(entry.id)
        board_ids = seen
        for entry in self.boards:
            for imp_id in entry.imports:
                if imp_id not in board_ids:
                    raise ValueError(
                        f"Board '{entry.id}' imports unknown board '{imp_id}'"
                    )
        return self


class NodeBlackboardRef(BaseModel):
    id: str
    read: bool = False
    write: bool = False
