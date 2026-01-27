import unittest
from pathlib import Path

from kegal.kegal import Compiler

CURRENT_DIR = Path(__file__).parent

class TestRagGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graph_tests" / "rag_graph.yml"

    def test_init(self):
        graph = Compiler(str(self.graph_path))

    def test_compile(self):
        graph = Compiler(str(self.graph_path))
        graph.compile()

    def test_compile_to_file(self):
        graph = Compiler(str(self.graph_path))
        graph.compile()
        graph.save_outputs_as_json(CURRENT_DIR / "graph_outputs" / "rag_graph" / "rag_graph.json")
        graph.save_outputs_as_markdown(CURRENT_DIR / "graph_outputs" / "rag_graph" / "rag_graph.md")

