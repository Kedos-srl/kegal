from kegal.graph_data import GraphData
from kegal.llm.llm_response import LlmResponse


def insert_user_message_to_graph_data(graph_data: GraphData, user_message: str):
    graph_data.nodes[0].prompt.placeholders["post"] = user_message


def insert_citations_to_graph_data(graph_data: GraphData, chunks: list[str]):
    """
     Insert citation chunks to the graph data nodes.

     The function adds citation chunks to nodes that contain a 'citations'
     placeholder in their prompts. All chunks are joined with newlines and set
     as the value of the 'citations' placeholder.

     :param graph_data: The graph data object containing nodes to be updated
     :type graph_data: GraphData
     :param chunks: List of citation text chunks to be added
     :type chunks: list[str]
     :return: The updated graph data object with citations added to relevant nodes
     :rtype: GraphData

     """
    nodes = graph_data.nodes
    for node in nodes:
        node_placeholders = node.prompt.placeholders
        if "citations" in node_placeholders:
            node_placeholders["citations"] = '\n'.join(chunks)
    return graph_data


def update_graph_data__history(graph_data: GraphData, responses: [LlmResponse]):
    """
    Updates the graph data with conversation history from LLM responses.

    The function processes LLM responses and updates corresponding nodes in the graph data.
    For each node that matches a response ID and contains a 'history' placeholder,
    it appends the conversation messages using the specified roles.


    :param graph_data: The graph data object containing nodes to be updated
    :type graph_data: GraphData

    :param responses: List of LLM response objects containing conversation messages
    :type responses: [LlmResponse]


    :return: The updated graph data object with modified history placeholders
    :rtype: GraphData

    """
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




