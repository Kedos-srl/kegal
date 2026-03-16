"""Integration tests for a two-node MCP sqlite chain graph."""
import unittest
from pathlib import Path

from kegal.compiler import Compiler

CURRENT_DIR = Path(__file__).parent
_GRAPH_URI = str(CURRENT_DIR / "graphs" / "mcp_sqlite_chain_graph.yml")


class TestMcpSqliteChainGraph(unittest.TestCase):

    def test_chain(self):
        """query_node fetches raw data, analyst_node produces a trend analysis."""
        compiler = Compiler(uri=_GRAPH_URI)
        try:
            compiler.compile()
            outputs = compiler.get_outputs()
            node_ids = [n.node_id for n in outputs.nodes]
            self.assertIn("query_node", node_ids)
            self.assertIn("analyst_node", node_ids)

            analyst_out = next(n for n in outputs.nodes if n.node_id == "analyst_node")
            self.assertIsNotNone(analyst_out.response.messages)
            answer = analyst_out.response.messages[0].lower()
            self.assertTrue(
                "widget" in answer or "revenue" in answer or "quarter" in answer,
                f"Unexpected answer: {answer}"
            )
            print(f"\nTrend analysis:\n{analyst_out.response.messages[0]}")
        finally:
            compiler.disconnect()

    def test_chain_to_file(self):
        compiler = Compiler(uri=_GRAPH_URI)
        try:
            compiler.compile()
            out_dir = CURRENT_DIR / "graph_outputs" / "mcp_sqlite_chain_graph"
            compiler.save_outputs_as_json(out_dir / "mcp_sqlite_chain_graph.json")
            compiler.save_outputs_as_markdown(out_dir / "mcp_sqlite_chain_graph.md")
        finally:
            compiler.disconnect()


if __name__ == "__main__":
    unittest.main()
