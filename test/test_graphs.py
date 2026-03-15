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


class TestDagGraph(unittest.TestCase):
    graph_path = CURRENT_DIR / "graphs" / "dag_graph.yml"

    def test_dag_levels(self):
        """Verify correct DAG scheduling order."""
        compiler = Compiler(uri=str(self.graph_path))
        deps = compiler._build_dag()
        levels = compiler._topological_levels(deps)

        def level_of(nid):
            return next(i for i, lvl in enumerate(levels) if nid in lvl)

        guard_lvl     = level_of("guard_node")
        summarizer_lvl = level_of("summarizer")
        analyst_a_lvl  = level_of("analyst_a")
        analyst_b_lvl  = level_of("analyst_b")

        # guard_node has no deps → first level
        self.assertIn("guard_node", levels[0])

        # summarizer depends on guard (guard is guard-node barrier)
        self.assertGreater(summarizer_lvl, guard_lvl)

        # analyst_a depends on summarizer (message_passing output→input)
        self.assertGreater(analyst_a_lvl, summarizer_lvl)

        # analyst_b is isolated → only depends on guard, so comes before analyst_a
        self.assertGreater(analyst_b_lvl, guard_lvl)
        self.assertLessEqual(analyst_b_lvl, analyst_a_lvl)

    def test_dag_compile(self):
        """Full DAG compilation must produce outputs for all four nodes."""
        compiler = Compiler(uri=str(self.graph_path))
        compiler.compile()
        outputs = compiler.get_outputs()
        executed_ids = {n.node_id for n in outputs.nodes}
        self.assertIn("guard_node", executed_ids)
        self.assertIn("summarizer", executed_ids)
        self.assertIn("analyst_a", executed_ids)
        self.assertIn("analyst_b", executed_ids)

    def test_dag_guard_blocks(self):
        """When guard returns validation=false the downstream nodes must NOT run."""
        compiler = Compiler(uri=str(self.graph_path))
        # Force guard to fail by replacing the user message with offensive content
        compiler.user_message = "You are all idiots and I hate this stupid system!!!"
        compiler.compile()
        outputs = compiler.get_outputs()
        executed_ids = {n.node_id for n in outputs.nodes}
        # Guard ran
        self.assertIn("guard_node", executed_ids)
        # Downstream nodes must not have run
        self.assertNotIn("summarizer", executed_ids)
        self.assertNotIn("analyst_a", executed_ids)
        self.assertNotIn("analyst_b", executed_ids)

    def test_dag_compile_to_file(self):
        compiler = Compiler(uri=str(self.graph_path))
        compiler.compile()
        out_dir = CURRENT_DIR / "graph_outputs" / "dag_graph"
        compiler.save_outputs_as_json(out_dir / "dag_graph.json")
        compiler.save_outputs_as_markdown(out_dir / "dag_graph.md")
