import base64
from typing import Any

import boto3

from .llm_model import (LlmModel,
                       LLMImageData,
                       LLMPdfData,
                       LLMTool,
                       LLmMessage,
                       LLMStructuredOutput,
                       LLMFunctionCall,
                       LLmResponse,
                       DEFAULT_JSON_OUTPUT_NAME)

from botocore.exceptions import ClientError


class LlmBedrock(LlmModel):
    """
        Documentation: https://docs.aws.amazon.com/nova/latest/userguide/complete-request-schema.html
    """
    def __init__(self, **kwarg):

        if "model" not in kwarg.keys():
            raise ValueError("Missing required 'model' parameter")
        if "aws_region_name" not in kwarg.keys():
            raise ValueError("Missing required 'region_name' parameter")

        super().__init__(kwarg.get("model"))
        self.client = boto3.client(service_name='bedrock-runtime',
                                   region_name=kwarg.get("aws_region_name"),
                                   aws_access_key_id=kwarg.get("aws_access_key"),
                                   aws_secret_access_key=kwarg.get("aws_secret_key"))

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


            # Force Model to structured json output esle us regualr tools
            if structured_output is not None:
                if "toolConfig" in body:
                    body["toolConfig"]["tools"].append(self._structured_output_data(structured_output))
                else:
                    body["toolConfig"] = {
                        "tools": [self._structured_output_data(structured_output)]
                    }
                body["toolConfig"]["toolChoice"] = {"tool": { "name": DEFAULT_JSON_OUTPUT_NAME }}



            #return self._get_response(json.dumps(body))
            return self._get_response(body)


    @staticmethod
    def _chat_message(message: str):
            return {
                "text": message
            }

    @staticmethod
    def _chat_history(history: list[LLmMessage]):
        return [
            {
                "role": chat.role,
                "content": [{"text": chat.content}]
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
    def _structured_output_data(structured_output: LLMStructuredOutput):
        return {
            "toolSpec": {
                "name": DEFAULT_JSON_OUTPUT_NAME,
                "description":"json output schema",
                "inputSchema": {
                    "json": structured_output.json_output.model_dump(exclude_none=True)
                }
            }
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

        if pdfs_b64 is not None:
            user_content.extend(self._pdfs_data(pdfs_b64))

        # Compoese user content
        messages.append({
            "role": "user",
            "content": user_content
        })

        return messages

    def _get_response(self, body) -> LLmResponse:
        try:
            #model_response = self.client.invoke_model(body=body, modelId=self.model)
            response_body = self.client.converse(**body)
            #response_body = json.loads(model_response.get("body").read())

            llm_response = LLmResponse()
            llm_response.input_size = response_body["usage"]["inputTokens"]
            llm_response.output_size = response_body["usage"]["outputTokens"]

            response_contents = response_body["output"]["message"]["content"]
            for response in response_contents:
                if "text" in response:
                    if llm_response.messages is None:
                        llm_response.messages = [response["text"]]
                    else:
                        llm_response.messages.append(response["text"])
                if "toolUse" in response:
                    tool_use = response["toolUse"]
                    if tool_use["name"] == DEFAULT_JSON_OUTPUT_NAME:
                        llm_response.json_output = tool_use["input"]
                    else:
                        function_call = LLMFunctionCall(
                            name=tool_use["name"],
                            parameters=tool_use["input"]
                        )
                        if llm_response.tools is None:
                            llm_response.tools = [function_call]
                        else:
                            llm_response.tools.append(function_call)

            return  llm_response
        except (ClientError, Exception) as e:
            error_msg = f"ERROR: Can't invoke '{self.model}' endpoint: {e}"
            raise RuntimeError(error_msg)
        finally:
            self.client.close()

