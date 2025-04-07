from .graph_data import LlmConfig
from .llm.llm_handler import  LlmHandler
from .llm.gpt_handler import GptHandler
from .llm.ollama_handler import OllamaHandler
from .llm.bedrock_handler import BedrockHandler
from .llm.llm_response import LlmResponse


GPT = "gpt"
OLLAMA = "ollama"
BEDROCK = "bedrock"

class LlmDispenser:
    """
    A class to manage and provide handlers for different types of Large Language Models (LLMs).
    It initializes the appropriate handler based on the provided configuration.

    :param llm_configs_: A list of LlmConfig objects containing the configurations for various LLMs.
    
    :raises ValueError: Raised when an unsupported LLM type is provided.
    """

    def __init__(self, llm_configs_: list[LlmConfig]):
        """
        Initialize the LlmDispenser with handlers for specified LLMs.

        :param self: Refers to the instance of the LlmDispenser class.
        :param llm_configs_: A list of LlmConfig objects for setting up handlers.
        """
        self.handlers: list[LlmHandler] = []
        for config in llm_configs_:
            if config.llm == GPT:
                self.handlers.append(GptHandler(
                    model_=config.version,
                    api_key_=config.api_key
                ))
            elif config.llm == OLLAMA:
                self.handlers.append(OllamaHandler(
                    model_=config.version,
                    host_=config.host
                ))
            elif config.llm == BEDROCK:
                self.handlers.append(BedrockHandler(
                    model_=config.version,
                    region_name_=config.aws_config.region,
                    access_key_=config.aws_config.access_key,
                    secret_key_=config.aws_config.secret_key
                ))
            else:
                raise ValueError(f"Invalid llm type: {config.llm}")

    def __getitem__(self, index_: int):
        """
        Retrieve an LLM handler by its index in the handlers list.

        :param self: Refers to the instance of the LlmDispenser class.
        :param index_: The index of the handler to retrieve.
        :return: The LlmHandler at the requested index.

        :raises IndexError: Raised if the provided index is out of range.
        """
        try:
            returning_handler = self.handlers[index_]
        except IndexError:
            raise IndexError("The provided index is out of range. No handler exists at the specified index.")
        return returning_handler


