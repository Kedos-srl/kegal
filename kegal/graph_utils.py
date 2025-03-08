from kegal.graph_data import GraphData
from kegal.llm.llm_response import LlmResponse


def update_graph_data__history(graph_data: GraphData, responses: [LlmResponse]):
    nodes = graph_data.nodes
    for response in responses:
        resp_id = response.node_id
        for node in nodes:
            node_id = node.id
            if node_id == resp_id:
                node_placeholders = node.prompt.placeholders

                if "history" in node_placeholders:
                    user_message = response.message_content
                    assistant_message = response.response_content

                    if "user_role" in node_placeholders:
                        user_role = node_placeholders["user_role"]
                        node_placeholders["history"] += f"\n\n{user_role}: {user_message}"
                    if "assistant_role" in node_placeholders:
                        assistant_role = node_placeholders["assistant_role"]
                        node_placeholders["history"] += f"\n\n{assistant_role}: {assistant_message}"
    return graph_data


def add_citations_to_graph_data(graph_data: GraphData, chunks: list[str]):
    nodes = graph_data.nodes
    for node in nodes:
        node_placeholders = node.prompt.placeholders
        if "citations" in node_placeholders:
            node_placeholders["citations"] = '\n'.join(chunks)
    return graph_data


