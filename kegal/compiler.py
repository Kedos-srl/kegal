import json
import time

from pathlib import Path
from typing import Any

from pydantic import BaseModel
from .compose import compose_template_prompt, compose_node_prompt, compose_images, compose_documents, compose_tools
from .graph import Graph
from .utils import load_contents
from .llm.llm_handler import LlmHandler
from .llm.llm_model import LLmResponse, LLMStructuredOutput, LLMStructuredSchema

import logging

logger = logging.getLogger(__name__)


class CompiledNodeOutput(BaseModel):
    node_id: str
    response: LLmResponse
    compiled_time: float
    show: bool 
    history: bool 

class CompiledOutput(BaseModel):
    nodes: list[CompiledNodeOutput] = []
    input_size: int = 0
    output_size: int = 0
    compile_time: float = 0


class Compiler:
    def __init__(self, uri: str | None = None,
                       source: dict | None = None) -> None:
        if uri is not None:
            graph = Graph.from_uri(uri)
        else:
            graph = Graph.model_validate(source)

        self.clients: list[LlmHandler] = [LlmHandler(**model.model_dump(exclude_none=True)) for model in graph.models]
        self.images = graph.images
        self.documents = graph.documents
        self.tools = graph.tools
        self.prompts = self._get_graph_prompts_templates(graph)
        self.chat_history = graph.chat_history
        self.user_message = graph.user_message
        self.retrieved_chunks = graph.retrieved_chunks
        self.outputs: CompiledOutput = CompiledOutput()
        self.message_passing: list[Any] = []
        self.nodes = {node.id: node for index, node in enumerate(graph.nodes)}
        self.edges = graph.edges

    @staticmethod
    def _get_graph_prompts_templates(graph):
        prompts_templates: list[dict[str, str]] = []
        for prompt_input in graph.prompts:
            if prompt_input.template is not None:
                prompts_templates.append(compose_template_prompt(prompt_input.template))
            elif prompt_input.uri is not None:
                prompts_templates.append(
                    compose_template_prompt(
                        load_contents(prompt_input.uri)
                    )
                )
            else:
                raise ValueError("Prompt input must have either 'template' or 'uri' defined")
        return prompts_templates

    def compile(self):
        for edge in self.edges:
            try:
                check = self._compile_node(self.nodes[edge.node])
                if check is False:
                    return
            except Exception as e:
                logger.exception(f"Failed to compile node '{edge.node}': {e}")
                continue
            if edge.children is not None:
                for child in edge.children:
                    try:
                        check = self._compile_node(self.nodes[child])
                        if check is False:
                            return
                    except Exception as e:
                        logger.exception(f"Failed to compile child node '{child}': {e}")
                        continue

    def _chat_history_check(self, node)-> bool:
        if node.prompt is None or node.prompt.chat_history is None or self.chat_history is None:
            return False
        return node.prompt.chat_history in self.chat_history

    def _images_check(self, node) -> bool:
        if node.images is None or self.images is None:
            return False
        return True

    def _documents_check(self, node) -> bool:
        if node.documents is None or self.documents is None:
            return False
        return True

    def _tools_check(self, node) -> bool:
        if node.tools is None or self.tools is None:
            return False
        return True

    def _compose_node_prompt(self, node):
        prompt_elements: dict[str, Any] = {
            "prompt_template": self.prompts[node.prompt.template]
        }

        if node.prompt.prompt_placeholders:
            prompt_elements["placeholders"] = node.prompt.prompt_placeholders
        else:
            prompt_elements["placeholders"] = {}

        if node.prompt.user_message:
            prompt_elements["user_message"] = self.user_message

        if node.message_passing.input:
            prompt_elements["message_passing"] = self.message_passing

        if node.prompt.retrieved_chunks:
            prompt_elements["retrieved_chunks"] = self.retrieved_chunks

        return compose_node_prompt(**prompt_elements)

    def _check_message_passing(self, response, node):
        if not node.message_passing.input and not node.message_passing.output:
            self.message_passing.clear()
            return
        if node.message_passing.output:
            if response.messages is not None and len(response.messages) > 0:
                self.message_passing.extend(response.messages)
            elif response.json_output is not None:
                self.message_passing.append(response.json_output)

    def _build_model_body(self, node) -> dict[str, Any]:
        """Assemble the kwargs dict for the LLM call from the node configuration."""
        body: dict[str, Any] = {
            "temperature": node.temperature,
            "max_tokens": node.max_tokens,
        }

        composed_prompt = self._compose_node_prompt(node)
        if composed_prompt["system"] != "":
            body["system_prompt"] = composed_prompt["system"]
        if composed_prompt["user"] != "":
            body["user_message"] = composed_prompt["user"]

        if self._chat_history_check(node):
            body["chat_history"] = self.chat_history[node.prompt.chat_history]

        if self._images_check(node):
            body["imgs_b64"] = compose_images(self.images, node.images)

        if self._documents_check(node):
            body["pdfs_b64"] = compose_documents(self.documents, node.documents)

        if self._tools_check(node):
            body["tools_data"] = compose_tools(self.tools, node.tools)

        if node.structured_output is not None:
            body["structured_output"] = LLMStructuredOutput(
                json_output=LLMStructuredSchema(**node.structured_output)
            )

        return body

    def _record_output(self, node, response: LLmResponse, compiled_time: float, enable_history: bool) -> None:
        """Append node result to outputs and update aggregate metrics."""
        self.outputs.nodes.append(
            CompiledNodeOutput(
                node_id=node.id,
                response=response,
                compiled_time=compiled_time,
                show=node.show,
                history=enable_history,
            )
        )
        self.outputs.input_size += response.input_size
        self.outputs.output_size += response.output_size
        self.outputs.compile_time += compiled_time

    @staticmethod
    def _check_validation_gate(response: LLmResponse) -> bool:
        """Return False if the response signals a failed guard-node validation, True otherwise.

        Guard nodes (e.g. content moderation, prompt-injection checks) signal
        failure by returning a structured output with ``"validation": false``.
        When absent or True, graph execution continues normally.
        """
        if response.json_output is not None and "validation" in response.json_output:
            return response.json_output["validation"]
        return True

    def _compile_node(self, node) -> bool:
        if node.prompt is None:
            return True

        start_time = time.time()
        model_body = self._build_model_body(node)
        enable_history = "chat_history" in model_body
        response: LLmResponse = self.clients[node.model].complete(**model_body)
        compiled_time = time.time() - start_time

        logger.debug(f"Node {node.id} compiled in {compiled_time:.10f} seconds")
        self._record_output(node, response, compiled_time, enable_history)
        self._check_message_passing(response, node)
        return self._check_validation_gate(response)

    def get_outputs(self) -> CompiledOutput:
        return self.outputs

    def get_outputs_json(self, indent: int) -> str:
        return json.dumps(self.outputs.model_dump(), indent=indent)

    def save_outputs_as_json(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.outputs.model_dump(), f, indent=4)

    def save_outputs_as_markdown(self, path: Path, only_content: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if only_content:
            md = ""
            for i, output in enumerate(self.outputs.nodes):
                if output.response.messages:
                    for message in output.response.messages:
                        md += message
                if i > 0:
                    md += "\n"
                    md += "---"
        else:
            md = "## Graph Response\n"
            md += f" * Token Input size: {self.outputs.input_size}\n"
            md += f" * Token Output size: {self.outputs.output_size}\n"
            md += f" * Compile time: {self.outputs.compile_time}\n"
            for output in self.outputs.nodes:
                md += f"### Node:  {output.node_id}\n"
                # if output.response.messages is not None:
                #     md += f"{output.response.messages}\n"
                if output.response.json_output is not None:
                    md += f"""```json\n {json.dumps(output.response.json_output, indent=4)} \n```\n"""
                if output.response.tools is not None:
                    md += f"""```json\n {json.dumps(output.response.tools, indent=4)} \n```\n"""
                md += f"\nToken Input size:  {output.response.input_size} \n "
                md += f" Token Output size:  {output.response.output_size} \n "

        with open(path, "w") as f:
            f.write(md)















