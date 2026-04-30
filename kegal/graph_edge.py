from pydantic import BaseModel, ConfigDict, model_validator


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: str
    children: list["GraphEdge"] | None = None  # fan-out: sub-task decomposition
    fan_in: list["GraphEdge"] | None = None    # aggregation: wait for all listed nodes
    react: list["GraphEdge"] | None = None     # ReAct: available agent subgraphs

    @model_validator(mode="after")
    def _check_mutual_exclusivity(self) -> "GraphEdge":
        if self.react is not None and self.children is not None:
            raise ValueError(
                f"Edge for node '{self.node}': 'react' and 'children' are mutually exclusive"
            )
        return self
