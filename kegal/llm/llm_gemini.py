import base64
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

from .llm_model import (
    LlmModel,
    LLMImageData,
    LLMPdfData,
    LLMTool,
    LLmMessage,
    LLMStructuredOutput,
    LLMFunctionCall,
    LLmResponse,
)

# JSON Schema type string → Gemini Type enum name
_TYPE_MAP = {
    "string":  "STRING",
    "number":  "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array":   "ARRAY",
    "object":  "OBJECT",
}


class LlmGemini(LlmModel):
    def __init__(self, **kwargs):
        if "model" not in kwargs:
            raise ValueError("Missing required 'model' parameter")
        if "api_key" not in kwargs:
            raise ValueError("Missing required 'api_key' parameter")

        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "google-genai package required. Install with: pip install kegal[gemini]"
            )

        super().__init__(kwargs["model"])
        self.client = genai.Client(api_key=kwargs["api_key"])

    def complete(self,
                 system_prompt: str | None = None,
                 user_message: str = "",
                 chat_history: list[LLmMessage] | None = None,
                 imgs_b64: list[LLMImageData] | None = None,
                 pdfs_b64: list[LLMPdfData] | None = None,
                 tools_data: list[LLMTool] | None = None,
                 structured_output: LLMStructuredOutput | None = None,
                 temperature: float = 0.5,
                 max_tokens: int = 3000) -> LLmResponse:

        from google.genai import types

        contents = []
        if chat_history:
            contents.extend(self._chat_history(chat_history))

        user_parts = []
        if user_message:
            user_parts.append(types.Part.from_text(text=user_message))
        if imgs_b64:
            user_parts.extend(self._images_data(imgs_b64))
        if pdfs_b64:
            user_parts.extend(self._pdfs_data(pdfs_b64))

        if user_parts:
            contents.append(types.Content(role="user", parts=user_parts))

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt
        if tools_data:
            config_kwargs["tools"] = [self._tools_data(tools_data)]
        if structured_output:
            config_kwargs.update(self._structured_output_data(structured_output))

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            llm_response = LLmResponse()
            usage = response.usage_metadata
            llm_response.input_size = getattr(usage, "prompt_token_count", 0) or 0
            llm_response.output_size = getattr(usage, "candidates_token_count", 0) or 0

            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        fc = LLMFunctionCall(
                            name=part.function_call.name,
                            parameters=dict(part.function_call.args),
                        )
                        if llm_response.tools is None:
                            llm_response.tools = [fc]
                        else:
                            llm_response.tools.append(fc)
                    elif part.text:
                        if self._is_json(part.text):
                            llm_response.json_output = json.loads(part.text)
                        else:
                            if llm_response.messages is None:
                                llm_response.messages = [part.text]
                            else:
                                llm_response.messages.append(part.text)

            return llm_response

        except Exception as e:
            logger.error(f"Can't invoke '{self.model}' endpoint: {e}")
            raise RuntimeError(f"Can't invoke '{self.model}' endpoint: {e}") from e

    @staticmethod
    def _chat_message(message: str):
        from google.genai import types
        return types.Part.from_text(text=message)

    @staticmethod
    def _chat_history(history: list[LLmMessage] | list[dict]):
        from google.genai import types
        contents = []
        for msg in history:
            role = msg["role"] if isinstance(msg, dict) else msg.role
            text = msg["content"] if isinstance(msg, dict) else msg.content
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(text=text)],
            ))
        return contents

    @staticmethod
    def _images_data(images_b64: list[LLMImageData]):
        from google.genai import types
        return [
            types.Part.from_bytes(
                data=base64.b64decode(img.image_b64),
                mime_type=img.media_type,
            )
            for img in images_b64
        ]

    @staticmethod
    def _pdfs_data(pdfs_b64: list[LLMPdfData]):
        from google.genai import types
        return [
            types.Part.from_bytes(
                data=base64.b64decode(pdf.doc_b64),
                mime_type="application/pdf",
            )
            for pdf in pdfs_b64
        ]

    @staticmethod
    def _tools_data(tools_data: list[LLMTool]):
        from google.genai import types

        def _to_schema(d: dict) -> "types.Schema":
            type_key = _TYPE_MAP.get(d.get("type", "string").lower(), "STRING")
            kw: dict[str, Any] = {"type": getattr(types.Type, type_key)}
            if "description" in d:
                kw["description"] = d["description"]
            if "enum" in d:
                kw["enum"] = d["enum"]
            if "properties" in d:
                kw["properties"] = {k: _to_schema(v) for k, v in d["properties"].items()}
            if "required" in d:
                kw["required"] = d["required"]
            if "items" in d and isinstance(d["items"], dict):
                kw["items"] = _to_schema(d["items"])
            return types.Schema(**kw)

        declarations = []
        for data in tools_data:
            tool_dict = data.model_dump(exclude_none=True)
            props = {k: _to_schema(v) for k, v in tool_dict["parameters"].items()}
            declarations.append(types.FunctionDeclaration(
                name=tool_dict["name"],
                description=tool_dict["description"],
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties=props,
                    required=tool_dict.get("required", []),
                ),
            ))
        return types.Tool(function_declarations=declarations)

    @staticmethod
    def _structured_output_data(structured_output: LLMStructuredOutput) -> dict:
        return {
            "response_mime_type": "application/json",
            "response_schema": structured_output.json_output.to_dict(),
        }
