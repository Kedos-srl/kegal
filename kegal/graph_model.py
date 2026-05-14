from pydantic import BaseModel, SecretStr


class GraphModel(BaseModel):
    llm: str
    model: str
    api_key: SecretStr | None = None
    host: str | None = None
    context_window: int | None = None
    aws_region_name: str | None = None
    aws_access_key: SecretStr | None = None
    aws_secret_key: SecretStr | None = None

    def model_dump(self, **kwargs):
        """Override to expose credential values as plain strings for LLM adapter kwargs."""
        data = super().model_dump(**kwargs)
        for field in ("api_key", "aws_access_key", "aws_secret_key"):
            if field in data and data[field] is not None:
                data[field] = data[field].get_secret_value()
        return data
