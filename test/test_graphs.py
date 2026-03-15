import unittest
from pathlib import Path

from kegal.compiler import Compiler

CURRENT_DIR = Path(__file__).parent


class TestRagGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "rag_graph.yml"

    def test_init(self):
        Compiler(uri=str(self.graph_path))

    def test_compile(self):
        graph = Compiler(uri=str(self.graph_path))
        graph.compile()

    def test_compile_to_file(self):
        graph = Compiler(uri=str(self.graph_path))
        graph.compile()
        out_dir = CURRENT_DIR / "graph_outputs" / "rag_graph"
        graph.save_outputs_as_json(out_dir / "rag_graph.json")
        graph.save_outputs_as_markdown(out_dir / "rag_graph.md")
