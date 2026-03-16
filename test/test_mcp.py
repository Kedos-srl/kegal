"""Integration tests for MCP orchestrator-managed tool execution."""
import sys
import unittest

from kegal.graph import Graph
from kegal.compiler import Compiler

_MCP_GRAPH_URI = "test/graphs/mcp_graph.yml"


def _load_graph_source() -> dict:
    """Load the MCP graph YAML and substitute __PYTHON__ with sys.executable."""
    graph = Graph.from_uri(_MCP_GRAPH_URI)
    data = graph.model_dump()
    for server in data.get("mcp_servers") or []:
        if server.get("command") == "__PYTHON__":
            server["command"] = sys.executable
    return data


class TestMcpGraph(unittest.TestCase):

    def test_mcp_tool_call(self):
        """Node should call get_weather via MCP and return a final text answer."""
        compiler = Compiler(source=_load_graph_source())
        try:
            compiler.compile()
            outputs = compiler.get_outputs()
            self.assertEqual(len(outputs.nodes), 1)
            node_out = outputs.nodes[0]
            self.assertEqual(node_out.node_id, "weather_node")
            self.assertIsNotNone(node_out.response.messages)
            self.assertTrue(len(node_out.response.messages) > 0)
            answer = node_out.response.messages[0].lower()
            self.assertTrue(
                "rome" in answer or "weather" in answer or "sunny" in answer,
                f"Unexpected answer: {answer}"
            )
            print(f"\nMCP tool answer: {node_out.response.messages[0]}")
        finally:
            compiler.disconnect()


if __name__ == "__main__":
    unittest.main()
