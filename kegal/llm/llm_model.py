import base64
import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field
import fitz
import logging



class LLMProcessingError(Exception):
    """Raised when an LLM processing error occurs."""
    pass


class LLmMessage(BaseModel):
    role: str
    content: str



class LLMImageData(BaseModel):
    media_type: str
    image_b64: str



class LLMPdfData(BaseModel):
    doc_b64: str


class LLMStructuredSchema(BaseModel):
    # ============================================================================
    # Meta-Schema Keywords
    # ============================================================================
    schema_: str | None = Field(default=None, alias="$schema", serialization_alias="$schema")
    id_: str | None = Field(default=None, alias="$id", serialization_alias="$id")
    ref: str | None = Field(default=None, alias="$ref", serialization_alias="$ref")
    defs: dict[str, Any] | None = Field(default=None, alias="$defs", serialization_alias="$defs")
    comment: str | None = Field(default=None, alias="$comment", serialization_alias="$comment")

    # ============================================================================
    # Core Type Keywords
    # ============================================================================
    type: str | list[str] | None = Field(default=None)
    enum: list[Any] | None = Field(default=None)
    const: Any | None = Field(default=None)

    # ============================================================================
    # Metadata/Annotation
    # ============================================================================
    title: str | None = Field(default=None)
    description: str | None = Field(default=None)
    default: Any | None = Field(default=None)
    examples: list[Any] | None = Field(default=None)
    deprecated: bool | None = Field(default=None)

    # ============================================================================
    # Numeric Constraints
    # ============================================================================
    multipleOf: float | int | None = Field(default=None)
    minimum: float | int | None = Field(default=None)
    maximum: float | int | None = Field(default=None)
    exclusiveMinimum: float | int | None = Field(default=None)
    exclusiveMaximum: float | int | None = Field(default=None)

    # ============================================================================
    # String Constraints
    # ============================================================================
    minLength: int | None = Field(default=None)
    maxLength: int | None = Field(default=None)
    pattern: str | None = Field(default=None)
    format: str | None = Field(default=None)

    # ============================================================================
    # Array Constraints
    # ============================================================================
    items: dict[str, Any] | bool | None = Field(default=None)
    prefixItems: list[dict[str, Any]] | None = Field(default=None)
    minItems: int | None = Field(default=None)
    maxItems: int | None = Field(default=None)
    uniqueItems: bool | None = Field(default=None)
    contains: dict[str, Any] | None = Field(default=None)

    # ============================================================================
    # Object Constraints
    # ============================================================================
    properties: dict[str, Any] | None = Field(default=None)
    patternProperties: dict[str, Any] | None = Field(default=None)
    additionalProperties: dict[str, Any] | bool | None = Field(default=None)
    required: list[str] | None = Field(default=None)
    minProperties: int | None = Field(default=None)
    maxProperties: int | None = Field(default=None)
    dependentRequired: dict[str, list[str]] | None = Field(default=None)

    # ============================================================================
    # Composition
    # ============================================================================
    allOf: list[dict[str, Any]] | None = Field(default=None)
    anyOf: list[dict[str, Any]] | None = Field(default=None)
    oneOf: list[dict[str, Any]] | None = Field(default=None)
    not_: dict[str, Any] | None = Field(default=None, alias="not", serialization_alias="not")

    # ============================================================================
    # Conditional
    # ============================================================================
    if_: dict[str, Any] | None = Field(default=None, alias="if", serialization_alias="if")
    then: dict[str, Any] | None = Field(default=None)
    else_: dict[str, Any] | None = Field(default=None, alias="else", serialization_alias="else")
    dependentSchemas: dict[str, dict[str, Any]] | None = Field(default=None)

    # ============================================================================
    # Configuration
    # ============================================================================

    model_config = {
        "extra": "allow",
        "populate_by_name": True,
    }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, excluding None values and using correct JSON Schema keys."""
        return self.model_dump(exclude_none=True, by_alias=True)

    def to_json_schema(self) -> dict[str, Any]:
        """Alias for to_dict() for clarity."""
        return self.to_dict()



class LLMTool(BaseModel):
    name: str
    description: str
    parameters: dict[str, LLMStructuredSchema]
    required: list[str]




DEFAULT_JSON_OUTPUT_NAME = "json_output_schema"
class LLMStructuredOutput(BaseModel):
    json_output: LLMStructuredSchema



class LLMFunctionCall(BaseModel):
    name: str
    parameters: dict




class LLmResponse(BaseModel):
    messages: list[str] =  Field(default=None)
    tools: list[LLMFunctionCall] | None =  Field(default=None)
    json_output: dict | None =  Field(default=None)
    input_size: int = 0
    output_size: int = 0



class LlmModel(ABC):
    """Abstract base class for all LLM handlers"""
    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def complete(self,
                 system_prompt: str | None,
                 user_message: str,
                 chat_history: list[LLmMessage],
                 imgs_b64: list[LLMImageData] | None,
                 pdfs_b64: list[LLMPdfData] | None,
                 tools_data: list[LLMTool] | None,
                 structured_output: LLMStructuredOutput | None,
                 temperature: float,
                 max_tokens: int) -> LLmResponse:
        pass

    # text -> text
    @staticmethod
    @abstractmethod
    def _chat_message(message: str):
        pass

    @staticmethod
    @abstractmethod
    def _chat_history(history: list[LLmMessage]):
        pass

    # text -> image
    @staticmethod
    @abstractmethod
    def _images_data(images_b64: list[LLMImageData]):
        pass

    # text -> pdf
    @staticmethod
    @abstractmethod
    def _pdfs_data(pdfs_b64: list[LLMPdfData]):
        pass

    # function calling
    @staticmethod
    @abstractmethod
    def _tools_data(tools_data: list[LLMTool]):
        pass

    @staticmethod
    @abstractmethod
    def _structured_output_data(structured_output: LLMStructuredOutput):
        pass


    @staticmethod
    def extract_format_from_media_type(media_type: str) -> str:
        if not media_type or '/' not in media_type:
            raise LLMProcessingError(f"Invalid media type: {media_type}\n"
                                     f"Media type non valido")

        try:
            subtype = media_type.split('/')[-1].lower()
            # Normalizza jpg → jpeg
            if subtype == 'jpg':
                subtype = 'jpeg'
            return subtype
        except Exception as e:
            raise LLMProcessingError(f"Error extracting format from media type\n"
                                     f"Failed to extract format: {e}") from e


    @staticmethod
    def extract_images_from_pdf(pdf: LLMPdfData):
        try:
            pdf_bytes = base64.b64decode(pdf.doc_b64)
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            images: list[LLMImageData] = []
            for page_index in range(len(pdf_document)):
                for img_index, img in enumerate(pdf_document.get_page_images(page_index)):
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_format = base_image["ext"]
                    images.append(
                        LLMImageData(
                            media_type=f"image/{image_format}",
                            image_b64=base64.b64encode(image_bytes).decode("utf-8")
                        )
                    )
            return images
        except Exception as e:
            raise LLMProcessingError(f"Error extracting images from PDF\n"
                                     f"Failed to extract images: {e}") from e

    @staticmethod
    def _is_json(myjson_string):
        if not isinstance(myjson_string, str):
            logging.debug(f"Not a string: {type(myjson_string)}")
            return False

        try:
            json.loads(myjson_string)
            return True
        except json.JSONDecodeError as e:
            logging.debug(f"Invalid JSON: {e}")
            return False




