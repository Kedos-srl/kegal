from typing import Any
from .graph import GraphInputData
from .llm.llm_model import LLMImageData, LLMPdfData, LLMTool
from .utils import load_images_to_base64, load_pdfs_to_base64


def compose_template_prompt(prompt_template: dict[str, Any]) -> dict[str, str]:

    system_output = ""
    if "system_template" in prompt_template:
        system_template = prompt_template["system_template"]

        for key, value in system_template.items():
            system_output += "<{}>\n".format(key)
            system_output +=  value
            system_output += "</{}>\n\n".format(key)

    user_output = ""
    if "prompt_template" in prompt_template:
        user_template = prompt_template["prompt_template"]

        for key, value in user_template.items():
            user_output += "<{}>\n".format(key)
            user_output += value
            user_output += "</{}>\n\n".format(key)
    return {
        "system": system_output,
        "user": user_output
    }



def compose_node_prompt(prompt_template: dict[str, str],
                        placeholders: dict,
                        user_message: str | None = None,
                        message_passing: list[str] | None = None,
                        retrieved_chunks: str | None = None):

    if user_message is not None:
        placeholders["user_message"] = user_message.strip()

    if message_passing is not None:
        placeholders["message_passing"]: str = str(message_passing).strip()

    if retrieved_chunks is not None:
        placeholders["retrieved_chunks"] = retrieved_chunks.strip()

    if len(placeholders) > 0:
        output = prompt_template.copy()
        output["system"] = output["system"].format(**placeholders)
        output["user"] = output["user"].format(**placeholders)
        return output
    return prompt_template

def compose_images(data: list[GraphInputData], indices: list[int]):
    imgs_b64: list[LLMImageData] = []
    for index in indices:
        input_data = data[index]
        content_type, base64_data = load_images_to_base64(input_data.uri if input_data.uri else input_data.base64)
        imgs_b64.append(LLMImageData(
                media_type=content_type,
                image_b64 = base64_data
            ) )
    return imgs_b64

def compose_documents(data: list[GraphInputData], indices: list[int]):
    pdfs_b64: list[LLMPdfData] = []
    for index in indices:
        input_data = data[index]
        content_type, base64_data = load_pdfs_to_base64(input_data.uri if input_data.uri else input_data.base64)
        pdfs_b64.append(LLMPdfData(
            doc_b64=base64_data)
        )
    return pdfs_b64

def compose_tools(tools: list[LLMTool], indices: list[int]):
    return [tools[i].template for i  in indices]


def _compose_llm_object() -> dict:
    pass