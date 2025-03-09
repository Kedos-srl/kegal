from llm.llm_handler import LlmHandler
from system_templates import SystemTemplates, SystemStringTemplate
from llm.llm_response import LlmResponse, validate_llm_response, get_response_message
from llm_dispenser import LlmDispenser
from graph_data import *
import networkx as nx






# ==============
# GRAPH EDGE
# ==============
class EdgeAttribs:
    """
      Represents a single node in the graph. Handles the interaction with LLM
      and manages node-specific data and responses.
      """

    CHAT_MESSAGES = "chat_messages"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    HISTORY = "history"
    EMPTY = "empty"


# ==============
# GRAPH NODE
# ==============
class NodeGraph:
    def __init__(self, node_data: NodeData):
        """
        Initializes a NodeGraph instance.

        :param node_data: The data required to configure this node.
        """
        self.data = node_data
        self.response = LlmResponse(
            id=self.data.id,
            message_content="",
            response_content= {},
            prompt_size=0,
            response_size=0
        )


    def __call__(self,
                 llm_dispenser: LlmDispenser,
                 systems_templates: SystemTemplates,
                 post_from_graph_: str | None) -> bool:
        """
        Executes the logic of the node when called. Interacts with the LLM to
        process messages and generate a response.

        :param llm_dispenser: An instance of LlmDispenser for model interaction.
        :param systems_templates: System-level message templates for formatting.
        :param post_from_graph_: A string input to this node from the graph.
        :return:
        """

        llm: LlmHandler = llm_dispenser[self.data.llm]
        system: SystemStringTemplate = systems_templates[self.data.prompt.system]

        placeholders = self.data.prompt.placeholders
        show = self.data.show
        history = None

        # prompt message
        if post_from_graph_ is not None and "post" in placeholders:
            placeholders["post"] = post_from_graph_
            self.response.message_content = post_from_graph_
        elif post_from_graph_ is None and  "post" in placeholders:
            self.response.message_content = placeholders["post"]

        # compose the message to be passed to the llm
        agent_prompt = system.substitute_placeholders(placeholders)

        # complete prompt
        completion = llm.complete(agent_prompt, self.data.temperature)

        # set response Object
        self.response.response_content = completion["content"]
        self.response.prompt_size = completion["input_size"]
        self.response.response_size = completion["output_size"]


        # update history
        assistant_message = get_response_message(self.response)
        if "history" in placeholders and placeholders["history"] is not None:
            if "user_role" in placeholders:
                placeholders["history"] += f"\n{placeholders['user_role']}: {placeholders['post']}"
            if "assistant_role" in placeholders:
                placeholders["history"] += f"\n{placeholders['assistant_role']}: {get_response_message(self.response)}"

        try:
            response = validate_llm_response(self.response)
            return response
        except ValueError as e:
            print(e)
            print(self.response)
            return False



    def show(self):
        return self.data.show


    def get_chat_messages(self) -> str:
        placeholders = self.data.prompt.placeholders
        message = placeholders["post"]
        if "post" in placeholders:
            if "user_role" in placeholders:
                user_role = placeholders["user_role"]
                message += f"{user_role}: {message}"
            if "assistant_role" in placeholders:
                assistant_role = placeholders["assistant_role"]
                message += f"{assistant_role}: {get_response_message(self.response)}"
            return message
        else:
            return ""


    def get_user_message(self) -> str:
        if "post" in self.data.prompt.placeholders:
            return self.data.prompt.placeholders["post"]
        else:
            return ""


    def get_assistant_message(self) -> str:
        if self.response is not None:
            return get_response_message(self.response)
        else:
            return ""

    def get_chat_history(self) -> str:
        if "history" in self.data.prompt.placeholders:
            return self.data.prompt.placeholders["history"]
        else:
            return ""


# ==================
# GRAPH COMPILER
# ==================
class GraphCompiler:
    def __init__(self, graph_data: GraphData):
        self.llm_dispenser = LlmDispenser(graph_data.models)

        self.system_templates = SystemTemplates(graph_data.systems)

        self.graph = nx.DiGraph()
        for node in graph_data.nodes:
            self.graph.add_node(node.id,
                                data=NodeGraph(node))

        self.start_node = None
        if graph_data.edges:
            for edge in graph_data.edges:
                self.graph.add_edge(edge.source,
                                    edge.target,
                                    data=edge.attrib)
            self.start_node = graph_data.edges[0].source

    def __call__(self):
        outputs: list[LlmResponse] = []

        if self.start_node is not None:
            agent_0: NodeGraph = self.graph.nodes[self.start_node]["data"]
            validate_agent_0 = agent_0(self.llm_dispenser,
                                       self.system_templates,
                                       None)

            if agent_0.show():
                outputs.append(agent_0.response)

            if validate_agent_0 is False:
                return outputs


            for src, trg in nx.edge_dfs(self.graph, source=self.start_node):
                agent_src: NodeGraph = self.graph.nodes[src]["data"]
                agent_trg: NodeGraph = self.graph.nodes[trg]["data"]
                edge_attrib = self.graph[src][trg]["data"]

                validate_agent = False
                if edge_attrib == EdgeAttribs.CHAT_MESSAGES:
                    validate_agent = agent_trg(self.llm_dispenser,
                                               self.system_templates,
                                               agent_src.get_chat_messages())
                elif edge_attrib == EdgeAttribs.USER_MESSAGE:
                    validate_agent = agent_trg(self.llm_dispenser,
                                               self.system_templates,
                                               agent_src.get_user_message())
                elif edge_attrib == EdgeAttribs.ASSISTANT_MESSAGE:
                    validate_agent = agent_trg(self.llm_dispenser,
                                               self.system_templates,
                                               agent_src.get_assistant_message())
                elif edge_attrib == EdgeAttribs.HISTORY:
                    validate_agent = agent_trg(self.llm_dispenser,
                                               self.system_templates,
                                               agent_src.get_chat_history())
                else:
                    validate_agent = agent_trg(self.llm_dispenser,
                                              self.system_templates,
                                    None)

                if agent_trg.show():
                    outputs.append(agent_trg.response)

                if validate_agent is False:
                    return outputs
        else:
            for node in self.graph.nodes:
                agent = self.graph.nodes[node]["data"]
                validate_agent = agent(self.llm_dispenser,
                                       self.system_templates,
                                       None)
                if agent.show():
                    outputs.append(agent.response)

        return outputs

    def __getitem__(self, id_: str):
        return self.graph.nodes[id_]["data"]

    def log_nodes_ids(self):
        for node in self.graph.nodes:
            print(node)


