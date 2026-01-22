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


class TestKeXtractExtractionGraph(unittest.TestCase):
    graph_path =  CURRENT_DIR / "graph_tests" / "kextract_extract_graph.yml"

    def test_init(self):
        graph = Compiler(str(self.graph_path))

    def test_compile_to_file(self):
        graph = Compiler(str(self.graph_path))
        graph.compile()
        graph.save_outputs_as_json(CURRENT_DIR / "graph_outputs" / "kextract_graph" / "kextract_struct_graph.json")
        graph.save_outputs_as_markdown(CURRENT_DIR / "graph_outputs" / "kextract_graph" / "kextract_struct_graph.md")

class TestKeXtractOCRGraph(unittest.TestCase):
    graph_path =  CURRENT_DIR / "graph_tests" /  "kextract_ocr_graph.yml"

    def test_init(self):
        graph = Compiler(str(self.graph_path))


    def test_compile_to_file(self):
        graph = Compiler(str(self.graph_path))
        graph.compile()
        print(graph.get_outputs())
        #graph.save_outputs_as_markdown(CURRENT_DIR / "graph_outputs" / "kextract_graph" / "kextract_ocr_graph.md")
        graph.save_outputs_as_markdown(Path("/home/fabio/Documents/Dataset/KeXtractOut/00040534_3.md"), only_content=True)