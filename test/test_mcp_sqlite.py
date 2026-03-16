"""Integration tests for MCP sqlite tool execution."""
import unittest
from pathlib import Path

from kegal.compiler import Compiler

CURRENT_DIR = Path(__file__).parent
_MCP_SQLITE_GRAPH_URI = str(CURRENT_DIR / "graphs" / "mcp_sqlite_graph.yml")


class TestMcpSqliteGraph(unittest.TestCase):

    def test_sqlite_tool_call(self):
        """LLM should query the sales DB via MCP and identify the top product."""
        compiler = Compiler(uri=_MCP_SQLITE_GRAPH_URI)
        try:
            compiler.compile()
            outputs = compiler.get_outputs()
            self.assertEqual(len(outputs.nodes), 1)
            node_out = outputs.nodes[0]
            self.assertEqual(node_out.node_id, "analyst_node")
            self.assertIsNotNone(node_out.response.messages)
            answer = node_out.response.messages[0].lower()
            # Widget A has the highest total: 12500+15200+13800+17100 = 58600
            self.assertIn("widget a", answer)
            print(f"\nSQLite MCP answer: {node_out.response.messages[0]}")
        finally:
            compiler.disconnect()

    def test_sqlite_tool_call_to_file(self):
        """Compile sqlite MCP graph and save outputs to graph_outputs/mcp_sqlite_graph/."""
        compiler = Compiler(uri=_MCP_SQLITE_GRAPH_URI)
        try:
            compiler.compile()
            out_dir = CURRENT_DIR / "graph_outputs" / "mcp_sqlite_graph"
            compiler.save_outputs_as_json(out_dir / "mcp_sqlite_graph.json")
            compiler.save_outputs_as_markdown(out_dir / "mcp_sqlite_graph.md")
        finally:
            compiler.disconnect()


if __name__ == "__main__":
    unittest.main()
