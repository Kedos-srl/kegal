import json
from typing import Any
from botocore.config import Config

from .llm_model import (LlmModel,
                       LLMImageData,
                       LLMPdfData,
                       LLMTool,
                       LLmMessage,
                       LLMStructuredOutput,
                       LLMFunctionCall,
                       LLmResponse,
                       DEFAULT_JSON_OUTPUT_NAME)

class LlmAnthropic(LlmModel):
    """
        Documentation:https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html
    """
    def __init__(self, **kwargs):
        if "model" not in kwargs.keys():
            raise ValueError

        super().__init__(kwargs.get("model"))

        if "api_key" in kwargs.keys():
            import anthropic

            self.client = anthropic.Anthropic(api_key=kwargs.get("api_key"))
            self.aws = False
        else:
            import boto3

            if "aws_region_name" not in kwargs.keys():
                raise ValueError("Missing required parameter: region_name")

            config = Config(
                read_timeout=300,  # Increase from 60 to 300 seconds
                connect_timeout=60,
                retries={'max_attempts': 3}
            )


            self.client = boto3.client(service_name='bedrock-runtime',
                                       region_name=kwargs.get("aws_region_name"),
                                       aws_access_key_id=kwargs.get("aws_access_key"),
                                       aws_secret_access_key=kwargs.get("aws_secret_key"),
                                       config=config)

            self.anthropic_version = "bedrock-2023-05-31"
            self.aws = True


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
        # Compose messages to pass to the model
        messages = self._compose_messages(
            user_message,
            chat_history,
            imgs_b64,
            pdfs_b64
        )

        # Model setup and chat messages
        body : dict[str, Any] = {
            "temperature": temperature,
            "messages": messages,
            "max_tokens": max_tokens
        }

        # Add system prompt if provided
        if system_prompt is not None:
            body["system"] = system_prompt



        if tools_data is not None:
            body["tools"] = self._tools_data(tools_data)

        # Force Model to structured json output
        if  structured_output is not None:
            if "tools" in body:
                body["tools"].append(self._structured_output_data(structured_output))
            else:
                body["tools"] = [self._structured_output_data(structured_output)]
            body["tool_choice"] =  {"type": "tool", "name": DEFAULT_JSON_OUTPUT_NAME}



        # Return Aws response
        return self._get_response(body)


    @staticmethod
    def _chat_message(message: str):
        return {
            "type": "text",
            "text": message
        }

    @staticmethod
    def _chat_history(history: list[LLmMessage] | list[dict]):
        # If history already contains dicts (from YAML), return them directly
        if history and isinstance(history[0], dict):
            return history
        # Otherwise, convert Pydantic objects to dicts
        return [chat.model_dump() for chat in history]

    @staticmethod
    def _images_data(images_b64: list[LLMImageData]):
        content = []
        for img in images_b64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.media_type,
                    "data": img.image_b64
                }
             })
        return content

    @staticmethod
    def _pdfs_data(pdfs_b64: list[LLMPdfData]):
        content = []
        for pdf in pdfs_b64:
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf.doc_b64
                }
            })
        return content

    @staticmethod
    def _tools_data(tools_data: list[LLMTool]):
        schemas = []
        for data in tools_data:
            tool_dict = data.model_dump(exclude_none=True)
            schemas.append({
                "name": tool_dict["name"],
                "description": tool_dict["description"],
                "input_schema": tool_dict
            })
        return schemas

    @staticmethod
    def _structured_output_data(structured_output: LLMStructuredOutput):
        return {
                "name": DEFAULT_JSON_OUTPUT_NAME,
                "description": "json output schema",
                "input_schema": structured_output.json_output.model_dump(exclude_none=True)
            }

    def _compose_messages(self,
                          user_message: str = "",
                          chat_history: list[LLmMessage] | None = None,
                          imgs_b64: list[LLMImageData] | None = None,
                          pdfs_b64: list[LLMPdfData] | None = None, ):
        # Inserting chat history if provided
        messages: list[dict] = []
        if chat_history is not None:
            messages.extend(self._chat_history(chat_history))

        # Insert input message
        user_content = [self._chat_message(user_message)]

        # Extend current user message with input images and pdfs
        if imgs_b64 is not None:
            user_content.extend(self._images_data(imgs_b64))

        if  pdfs_b64 is not None:
            user_content.extend(self._pdfs_data(pdfs_b64))

        # Compoese user content
        messages.append({
            "role": "user",
            "content": user_content
        })

        return messages

    def _get_aws_response(self, body):
        try:
            body["anthropic_version"] = self.anthropic_version
            model_response = self.client.invoke_model(body=json.dumps(body), modelId=self.model)
            response_body = json.loads(model_response.get("body").read())

            llm_response = LLmResponse()
            llm_response.input_size = response_body["usage"]["input_tokens"]
            llm_response.output_size = response_body["usage"]["output_tokens"]

            response_contents = response_body["content"]
            for response in response_contents:
                if response["type"] == "text":
                    if llm_response.messages is None:
                        llm_response.messages = [response["text"]]
                    else:
                        llm_response.messages.append(response["text"])
                if response["type"] == "tool_use":
                    if response["name"] == DEFAULT_JSON_OUTPUT_NAME:
                        llm_response.json_output = response["input"]
                    else:
                        function_call = LLMFunctionCall(
                            name=response["name"],
                            parameters=response["input"]
                        )
                        if llm_response.tools is None:
                            llm_response.tools = [function_call]
                        else:
                            llm_response.tools.append(function_call)

            return llm_response

        except Exception as e:
            error_msg = f"ERROR: Can't invoke '{self.model}' endpoint: {e}"
            raise RuntimeError(error_msg)


    def _get_anthropic_response(self, body):
        try:
            body["model"] = self.model
            response_body = self.client.messages.create(**body)

            llm_response = LLmResponse()
            llm_response.input_size = response_body.usage.input_tokens
            llm_response.output_size = response_body.usage.output_tokens

            response_contents = response_body.content
            for block in response_contents:
                if  block.type == "text":
                    if llm_response.messages is None:
                        llm_response.messages = [block.text]
                    else:
                        llm_response.messages.append(block.text)
                if block.type == "tool_use":
                    if block.name == DEFAULT_JSON_OUTPUT_NAME:
                        llm_response.json_output = block.input
                    else:
                        function_call = LLMFunctionCall(
                            name=block.name,
                            parameters=block.input
                        )
                        if llm_response.tools is None:
                            llm_response.tools = [function_call]
                        else:
                            llm_response.tools.append(function_call)

            return llm_response
        except Exception as e:
            error_msg = f"ERROR: Can't invoke '{self.model}' endpoint: {e}"
            raise RuntimeError(error_msg)
    # Manager response
    def _get_response(self, body) ->LLmResponse:
        if self.aws:
            return self._get_aws_response(body)
        else:
            return self._get_anthropic_response(body)



