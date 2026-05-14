import re
from typing import Any
from .graph import GraphInputData
from .llm.llm_model import LLMImageData, LLMPdfData, LLMTool
from .utils import load_images_to_base64, load_pdfs_to_base64

# Only allow XML-safe tag names: start with letter/underscore, then word chars or hyphens.
_SAFE_TAG = re.compile(r'^[A-Za-z_][A-Za-z0-9_\-]*$')


def _safe_tag(key: str) -> str:
    """Sanitise a YAML key for use as an XML tag name."""
    if not _SAFE_TAG.match(key):
        # Replace any unsafe characters with underscores
        sanitised = re.sub(r'[^A-Za-z0-9_\-]', '_', key)
        if not sanitised or not sanitised[0].isalpha() and sanitised[0] != '_':
            sanitised = '_' + sanitised
        return sanitised
    return key


def compose_template_prompt(prompt_template: dict[str, Any]) -> dict[str, str]:

    system_output = ""
    if "system_template" in prompt_template:
        system_template = prompt_template["system_template"]

        for key, value in system_template.items():
            tag = _safe_tag(key)
            system_output += "<{}>\n".format(tag)
            system_output +=  value
            system_output += "</{}>\n\n".format(tag)

    user_output = ""
    if "prompt_template" in prompt_template:
        user_template = prompt_template["prompt_template"]

        for key, value in user_template.items():
            tag = _safe_tag(key)
            user_output += "<{}>\n".format(tag)
            user_output += value
            user_output += "</{}>\n\n".format(tag)
    return {
        "system": system_output,
        "user": user_output
    }



def compose_node_prompt(prompt_template: dict[str, str],
                        placeholders: dict,
                        user_message: str | None = None,
                        message_passing: list | None = None,
                        retrieved_chunks: str | None = None):

    placeholders = dict(placeholders)  # copy — never mutate the caller's dict

    if user_message is not None:
        placeholders["user_message"] = user_message.strip()

    if message_passing is not None:
        placeholders["message_passing"] = "\n\n".join(str(m) for m in message_passing).strip()

    if retrieved_chunks is not None:
        placeholders["retrieved_chunks"] = retrieved_chunks.strip()

    if len(placeholders) > 0:
        output = prompt_template.copy()
        # Escape curly braces in VALUES so that user-controlled content (e.g.
        # user_message containing "{x}") is not interpreted as a nested format spec.
        safe_placeholders = {
            k: v.replace("{", "{{").replace("}", "}}") if isinstance(v, str) else v
            for k, v in placeholders.items()
        }
        try:
            output["system"] = output["system"].format(**safe_placeholders)
            output["user"]   = output["user"].format(**safe_placeholders)
        except KeyError as e:
            raise KeyError(
                f"Placeholder {e} used in prompt template but not activated in the node config. "
                f"Available placeholders: {list(placeholders.keys())}"
            ) from e
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

def compose_tools(tools: list[LLMTool], names: list[str]) -> list[LLMTool]:
    return [t for t in tools if t.name in names]
