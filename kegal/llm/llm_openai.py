import json
from typing import Any

import openai
from .llm_model import (LlmModel,
                       LLMImageData,
                       LLMPdfData,
                       LLMTool,
                       LLmMessage,
                       LLMStructuredOutput,
                       LLMFunctionCall,
                       LLmResponse)

class LllmOpenai(LlmModel):
    def __init__(self, **kwargs):
        if "model" not in kwargs.keys():
            raise ValueError("Missing required 'model' parameter")
        if "api_key" not in kwargs.keys():
            raise ValueError("Missing required 'api_key' parameter")
        super().__init__(kwargs.get("model"))
        self.client = openai.OpenAI(api_key=kwargs.get("api_key"))

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

        messages = self._compose_messages(system_prompt,
                                          user_message,
                                          chat_history,
                                          imgs_b64)

        tools = None
        if tools_data is not None:
            tools = self._tools_data(tools_data)

        json_format = None
        if structured_output is not None:
            json_format = self._structured_output_data(structured_output)

        try:
            model_response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                response_format=json_format
            )

            llm_response = LLmResponse()
            llm_response.input_size = model_response.usage.prompt_tokens
            llm_response.output_size = model_response.usage.completion_tokens

            for choice in model_response.choices:
                msg = choice.message
                if msg.content:
                    if self._is_json(msg.content):
                        llm_response.json_output = json.loads(msg.content)
                    else:
                        if llm_response.messages is None:
                            llm_response.messages = [msg.content]
                        else:
                            llm_response.messages.append(msg.content)
                if msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        function_call = LLMFunctionCall(
                            name=tool_call.function.name,
                             parameters=json.loads(tool_call.function.arguments)
                        )
                        if llm_response.tools is None:
                            llm_response.tools = [function_call]
                        else:
                            llm_response.tools.append(function_call)

            return llm_response
        except Exception as e:
            error_msg = f"ERROR: Can't invoke '{self.model}' endpoint: {e}"
            raise RuntimeError(error_msg)


    # text -> text
    @staticmethod
    def _chat_message(message: str):
        return {
            "type": "text",
            "text": message
        }

    @staticmethod
    def _chat_history(history: list[LLmMessage] | list[dict]):
        return [
            {
                "role": chat["role"] if isinstance(chat, dict) else chat.role,
                "content": chat["content"] if isinstance(chat, dict) else chat.content
            }
            for chat in history
        ]

    # text -> image
    @staticmethod
    def _images_data(images_b64: list[LLMImageData]):
        content = []
        for img in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img.media_type};base64,{img.image_b64}"
                }
            })
        return content

    # text -> pdf
    @staticmethod
    def _pdfs_data(pdfs_b64: list[LLMPdfData]):
        print("Openai does not directly support pdf, convert pdf to b64 image list ")

    # function calling
    @staticmethod
    def _tools_data(tools_data: list[LLMTool]):
        schemas: list[dict[str, Any]] = []
        for data in tools_data:
            tool_dict = data.model_dump(exclude_none=True)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name":  tool_dict["name"],
                        "description": tool_dict["description"],
                        "parameters": {
                            "type": "object",
                            "properties": tool_dict["parameters"],
                            "required": tool_dict["required"]
                        }
                    }
                }
            )
        return schemas

    @staticmethod
    def _structured_output_data(structured_output: LLMStructuredOutput):
        return structured_output.json_output.model_dump(exclude_none=True)


    def _compose_messages(self,
                          system_message: str | None,
                          user_message: str,
                          chat_history: list[LLmMessage] | None,
                          imgs_b64: list[LLMImageData] | None):

        messages: list[dict] = []
        if system_message is not None:
            messages = [{
                "role": "system",
                "content": system_message
            }]

        if chat_history is not None:
            messages.extend(self._chat_history(chat_history))

        # Insert input message
        user_content = [self._chat_message(user_message)]

        # Extend current user message with input images and pdfs
        if imgs_b64 is not None:
            user_content.extend(self._images_data(imgs_b64))


        # Compoese user content
        messages.append({
            "role": "user",
            "content": user_content
        })

        return messages