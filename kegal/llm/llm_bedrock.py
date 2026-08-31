import base64
import json
from typing import Any

from .llm_model import (LlmModel,
                       LLMImageData,
                       LLMPdfData,
                       LLMTool,
                       LLmMessage,
                       LLMStructuredOutput,
                       LLMFunctionCall,
                       LLmResponse,
                       DEFAULT_JSON_OUTPUT_NAME)


class LlmBedrock(LlmModel):
    """Non-Anthropic (and optionally Anthropic) models via the AWS Bedrock Converse API.

    IMPORTANT — two Bedrock code paths exist in this codebase:
      - LlmBedrock uses boto3 converse (this class, with botocore retry Config).
      - LlmAnthropic(aws=True) uses boto3 invoke_model with botocore retry Config.

    Changes to error handling, retry logic, or tool formats must be applied to BOTH paths
    or the behaviour will silently diverge. The long-term fix is to route all Anthropic-on-
    Bedrock traffic through this class and remove the aws=True branch in LlmAnthropic.

    Structured output uses Bedrock's NATIVE structured output API (``outputConfig.textFormat``
    with a ``json_schema`` type), i.e. constrained decoding enforced by Bedrock. It is NOT
    emulated via a forced tool call any more. Consequences:
      - Only models that support ``outputConfig`` can use ``structured_output`` through this
        class (Anthropic Claude 4.5 and recent open-weight models such as Kimi/Moonshot,
        Qwen, DeepSeek, Mistral). Older models (Claude 3.x, Amazon Nova) return a
        ``ValidationException``.
      - Real ``toolConfig`` tools and ``outputConfig`` now coexist without conflict.
      - If a model still answers with free text instead of the JSON, ``_get_response``
        raises a ``RuntimeError`` instead of silently returning ``json_output=None``.

    Converse API docs: https://docs.aws.amazon.com/nova/latest/userguide/complete-request-schema.html
    """

    # Bedrock stopReason values that indicate the structured response is unusable.
    _BAD_STRUCTURED_STOP_REASONS = {"malformed_model_output", "content_filtered"}
    def __init__(self, **kwarg):

        if "model" not in kwarg.keys():
            raise ValueError("Missing required 'model' parameter")
        if "aws_region_name" not in kwarg.keys():
            raise ValueError("Missing required 'aws_region_name' parameter")

        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise ImportError("boto3 package required. Install with: pip install kegal[aws]")

        config = Config(
            read_timeout=kwarg.get("aws_read_timeout", 60),
            connect_timeout=kwarg.get("aws_connect_timeout", 60),
            retries={'max_attempts': kwarg.get("aws_retries", 3)}
        )

        super().__init__(kwarg.get("model"))
        self.client = boto3.client(service_name='bedrock-runtime',
                                   region_name=kwarg.get("aws_region_name"),
                                   aws_access_key_id=kwarg.get("aws_access_key"),
                                   aws_secret_access_key=kwarg.get("aws_secret_key"),
                                   config=config)

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


            messages = self._compose_messages(
                user_message,
                chat_history,
                imgs_b64,
                pdfs_b64
            )

            # Model setup and chat messages
            body: dict[str, Any] = {
                "modelId": self.model,
                "inferenceConfig": {
                    "temperature": temperature,
                    "maxTokens": max_tokens
                },
                "messages": messages
            }

            # Add system prompt if provided
            if system_prompt is not None:
                body["system"] = [self._chat_message(system_prompt)]


            if tools_data is not None:
                body["toolConfig"] = {
                     "tools": self._tools_data(tools_data)
                 }


            # Native structured output — constrained decoding enforced by Bedrock.
            # Coexists with real toolConfig tools (no forced toolChoice any more).
            if structured_output is not None:
                body["outputConfig"] = self._structured_output_data(structured_output)

            return self._get_response(body)


    @staticmethod
    def _chat_message(message: str):
            return {
                "text": message
            }

    @staticmethod
    def _chat_history(history: list[LLmMessage] | list[dict]):
        return [
            {
                "role": chat["role"] if isinstance(chat, dict) else chat.role,
                "content": [{"text": chat["content"] if isinstance(chat, dict) else chat.content}]
            }
            for chat in history
        ]

    @staticmethod
    def _images_data(images_b64: list[LLMImageData]):
        content = []
        for img in images_b64:
            content.append({
                "image": {
                    "format": LlmModel.extract_format_from_media_type(img.media_type),
                    "source":{
                        "bytes":  base64.b64decode(img.image_b64)
                    }
                }
            })
        return content

    @staticmethod
    def _pdfs_data(pdfs_b64: list[LLMPdfData]):
        content = []
        for i, pdf in enumerate(pdfs_b64):
            content.append({
                "document": {
                    "format": "pdf",
                    "name": f"doc_{i}",
                    "source": {
                        "bytes": base64.b64decode(pdf.doc_b64)
                    }
                }
            })
        return content

    @staticmethod
    def _tools_data(tools_data: list[LLMTool]):
        schemas = []
        for data in tools_data:
            tool_dict = data.model_dump(exclude_none=True)
            schemas.append(
                {
                    "toolSpec":{
                        "name": tool_dict["name"],
                        "description": tool_dict["description"],
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": tool_dict["parameters"],
                                "required": tool_dict["required"]
                            }
                        }
                    }
                }
            )
        return  schemas

    @staticmethod
    def _force_no_additional_props(schema: Any) -> Any:
        """Recursively set ``additionalProperties: false`` on every object node.

        Bedrock's native structured output rejects a schema whose object nodes do not
        explicitly forbid additional properties. This rewrites the schema in place-safe
        fashion (returns a new structure) and only fills the key where it is missing, so
        an author who deliberately set ``additionalProperties`` keeps their value.
        """
        if isinstance(schema, list):
            return [LlmBedrock._force_no_additional_props(item) for item in schema]
        if not isinstance(schema, dict):
            return schema

        out = {k: LlmBedrock._force_no_additional_props(v) for k, v in schema.items()}
        is_object = out.get("type") == "object" or "properties" in out
        if is_object and "additionalProperties" not in out:
            out["additionalProperties"] = False
        return out

    @staticmethod
    def _structured_output_data(structured_output: LLMStructuredOutput):
        schema = LlmBedrock._force_no_additional_props(
            structured_output.json_output.to_dict()
        )
        return {
            "textFormat": {
                "type": "json_schema",
                "structure": {
                    "jsonSchema": {
                        "schema": json.dumps(schema),
                        "name": DEFAULT_JSON_OUTPUT_NAME,
                        "description": "json output schema",
                    }
                },
            }
        }


    def _compose_messages(self,
                          user_message: str | None = None,
                          chat_history: list[LLmMessage] | None = None,
                          imgs_b64: list[LLMImageData] | None = None,
                          pdfs_b64: list[LLMPdfData] | None = None, ):
        # Inserting chat history if provided
        messages: list[dict] = []
        if chat_history is not None:
            messages.extend(self._chat_history(chat_history))

        user_content: list[dict] = []
        if user_message:
            user_content.append(self._chat_message(user_message))
        if imgs_b64 is not None:
            user_content.extend(self._images_data(imgs_b64))
        if pdfs_b64 is not None:
            user_content.extend(self._pdfs_data(pdfs_b64))

        if user_content:
            messages.append({
                "role": "user",
                "content": user_content
            })

        return messages

    def _get_response(self, body) -> LLmResponse:
        from botocore.exceptions import ClientError
        try:
            response_body = self.client.converse(**body)

            llm_response = LLmResponse()
            llm_response.input_size = response_body["usage"]["inputTokens"]
            llm_response.output_size = response_body["usage"]["outputTokens"]

            response_contents = response_body["output"]["message"]["content"]
            stop_reason = response_body.get("stopReason")

            # Native structured output: the JSON arrives as a plain text block.
            if "outputConfig" in body:
                text = "".join(
                    part["text"] for part in response_contents if "text" in part
                ).strip()
                if stop_reason in self._BAD_STRUCTURED_STOP_REASONS:
                    raise RuntimeError(
                        f"'{self.model}' returned no usable structured output "
                        f"(stopReason={stop_reason}): {text[:500]!r}"
                    )
                try:
                    llm_response.json_output = json.loads(text)
                except (json.JSONDecodeError, TypeError) as e:
                    raise RuntimeError(
                        f"'{self.model}' was asked for structured output but did not "
                        f"return valid JSON (stopReason={stop_reason}): {text[:500]!r}"
                    ) from e
                return llm_response

            for response in response_contents:
                if "text" in response:
                    if llm_response.messages is None:
                        llm_response.messages = [response["text"]]
                    else:
                        llm_response.messages.append(response["text"])
                if "toolUse" in response:
                    tool_use = response["toolUse"]
                    function_call = LLMFunctionCall(
                        name=tool_use["name"],
                        parameters=tool_use["input"]
                    )
                    if llm_response.tools is None:
                        llm_response.tools = [function_call]
                    else:
                        llm_response.tools.append(function_call)

            return  llm_response
        except ClientError as e:
            raise RuntimeError(f"Can't invoke '{self.model}' endpoint: {e}") from e

    def close(self) -> None:
        """Close the underlying boto3 client and release its connections."""
        self.client.close()

