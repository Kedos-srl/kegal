import json
import logging
from typing import Any

from ollama import Client

logger = logging.getLogger(__name__)
from .llm_model import (LlmModel,
                       LLMImageData,
                       LLMPdfData,
                       LLMTool,
                       LLmMessage,
                       LLMStructuredOutput,
                       LLMFunctionCall,
                       LLmResponse)




class LlmOllama(LlmModel):
    def __init__(self, **kwargs):
        if "model" not in kwargs.keys():
            raise ValueError("Missing required 'model' parameter")
        super().__init__(kwargs.get("model"))
        self.client = Client(host=kwargs.get("host", "http://localhost:11434"))

    def close(self):
        self.client._client.close()

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
            system_prompt,
            user_message,
            chat_history,
            imgs_b64
        )

        options = {
            "temperature": temperature
        }

        tools: list | None = None
        if tools_data is not None:
            tools = self._tools_data(tools_data)

        json_format  = None
        if structured_output is not None:
            json_format = self._structured_output_data(structured_output)


        try:
            model_response = self.client.chat(
                model=self.model,
                messages=messages,
                tools=tools,
                format=json_format,
                options=options
            )

            llm_response = LLmResponse()
            llm_response.input_size =  model_response['prompt_eval_count']
            llm_response.output_size =  model_response['eval_count']

            contents = [model_response['message']["content"]]
            for item in contents:
                if self._is_json(item):
                    llm_response.json_output = json.loads(item)
                else:
                    if llm_response.messages is None:
                        llm_response.messages = [item]
                    else:
                        llm_response.messages.append(item)

            if "tool_calls" in model_response["message"]:
                tool_calls = model_response["message"]["tool_calls"]
                for tool in tool_calls:
                    function_name = tool['function']['name']
                    arguments = tool['function']['arguments']
                    function_call = LLMFunctionCall(
                        name=function_name,
                        parameters=arguments
                    )
                    if llm_response.tools is None:
                        llm_response.tools = [function_call]
                    else:
                        llm_response.tools.append(function_call)
            return llm_response
        except Exception as e:
            raise RuntimeError(f"Can't invoke '{self.model}' endpoint: {e}") from e


    @staticmethod
    def _chat_message(message: str) -> dict:
        return {"role": "user", "content": message}

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
        return [img.image_b64 for img in images_b64]

    # text -> pdf
    @staticmethod
    def _pdfs_data(pdfs_b64: list[LLMPdfData]):
        logger.warning("Ollama does not directly support PDF input")
        raise NotImplementedError("Ollama does not support PDF input; convert PDFs to base64 image lists first")

    # function calling
    @staticmethod
    def _tools_data(tools_data: list[LLMTool]):
        schemas = []
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
        messages = []
        if system_message is not None:
            messages = [{
                "role": "system",
                "content": system_message
            }]

        if chat_history is not None:
            messages.extend(self._chat_history(chat_history))

        user_data: dict[str, Any] = {
            "role": "user",
            "content": user_message
        }


        if imgs_b64 is not None:
            user_data["images"] = self._images_data(imgs_b64)

        messages.append(user_data)

        return messages

