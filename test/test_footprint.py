"""Tests for the footprint pipeline element.

Structure mirrors test_graphs.py:
  - Model/parsing unit tests   — no LLM, no YAML
  - DAG inference unit tests   — no LLM, lightweight _make_compiler helper
  - Integration tests          — load footprint_graph.yml, require Ollama
"""

import unittest
from pathlib import Path

from kegal.compiler import Compiler
from kegal.graph import Graph, NodeFootprint

CURRENT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_graphs.py style)
# ---------------------------------------------------------------------------

def _make_compiler(nodes_cfg: list, edges_cfg: list) -> Compiler:
    source = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": nodes_cfg,
        "edges": edges_cfg,
    }
    graph = Graph.model_validate(source)
    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    return c


def _node(nid: str, fp_read: bool = False, fp_write: bool = False) -> dict:
    n: dict = {
        "id": nid, "model": 0, "temperature": 0.0, "max_tokens": 10,
        "show": False,
        "message_passing": {"input": False, "output": False},
        "prompt": {"template": 0},
    }
    if fp_read or fp_write:
        n["footprint"] = {"read": fp_read, "write": fp_write}
    return n


def _level_of(levels: list, nid: str) -> int:
    return next(i for i, lvl in enumerate(levels) if nid in lvl)


# ---------------------------------------------------------------------------
# NodeFootprint model
# ---------------------------------------------------------------------------

class TestNodeFootprintModel(unittest.TestCase):

    def test_defaults_are_false(self):
        fp = NodeFootprint()
        self.assertFalse(fp.read)
        self.assertFalse(fp.write)

    def test_read_only(self):
        fp = NodeFootprint(read=True)
        self.assertTrue(fp.read)
        self.assertFalse(fp.write)

    def test_write_only(self):
        fp = NodeFootprint(write=True)
        self.assertFalse(fp.read)
        self.assertTrue(fp.write)

    def test_both_true(self):
        fp = NodeFootprint(read=True, write=True)
        self.assertTrue(fp.read)
        self.assertTrue(fp.write)


# ---------------------------------------------------------------------------
# Graph YAML parsing
# ---------------------------------------------------------------------------

class TestGraphParsing(unittest.TestCase):

    def _source(self, footprints=None, node_footprint=None):
        node = {
            "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 10,
            "show": False, "message_passing": {"input": False, "output": False},
            "prompt": {"template": 0},
        }
        if node_footprint:
            node["footprint"] = node_footprint
        return {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {}}],
            "footprints": footprints,
            "nodes": [node],
            "edges": [],
        }

    def test_footprints_absent_is_none(self):
        src = self._source()
        del src["footprints"]
        self.assertIsNone(Graph.model_validate(src).footprints)

    def test_footprints_inline_string(self):
        graph = Graph.model_validate(self._source(footprints="# Seed\n"))
        self.assertEqual(graph.footprints, "# Seed\n")

    def test_node_footprint_parsed(self):
        graph = Graph.model_validate(self._source(node_footprint={"read": True, "write": True}))
        self.assertTrue(graph.nodes[0].footprint.read)
        self.assertTrue(graph.nodes[0].footprint.write)

    def test_node_without_footprint_is_none(self):
        self.assertIsNone(Graph.model_validate(self._source()).nodes[0].footprint)


# ---------------------------------------------------------------------------
# _load_footprints — file path vs. plain string vs. None
# ---------------------------------------------------------------------------

class TestLoadFootprints(unittest.TestCase):

    def test_none_returns_empty(self):
        content, path = Compiler._load_footprints(None)
        self.assertEqual(content, "")
        self.assertIsNone(path)

    def test_plain_string_returned_as_is(self):
        content, path = Compiler._load_footprints("# Hello")
        self.assertEqual(content, "# Hello")
        self.assertIsNone(path)

    def test_existing_file_loaded(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                        delete=False, encoding="utf-8") as f:
            f.write("# From file")
            fpath = f.name
        try:
            content, path = Compiler._load_footprints(fpath)
            self.assertEqual(content, "# From file")
            self.assertEqual(path, Path(fpath))
        finally:
            os.unlink(fpath)

    def test_non_existing_path_treated_as_string(self):
        val = "/no/such/file.md"
        content, path = Compiler._load_footprints(val)
        self.assertEqual(content, val)
        self.assertIsNone(path)


# ---------------------------------------------------------------------------
# DAG stage-4: footprint write→read inference (no LLM)
# ---------------------------------------------------------------------------

class TestFootprintDagInference(unittest.TestCase):

    def _build(self, nodes, edges):
        c = _make_compiler(nodes, edges)
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        return deps, levels

    def test_read_depends_on_prior_write(self):
        deps, _ = self._build(
            [_node("W", fp_write=True), _node("R", fp_read=True)],
            [],
        )
        self.assertIn("W", deps["R"])

    def test_read_before_write_no_dep(self):
        deps, _ = self._build(
            [_node("R", fp_read=True), _node("W", fp_write=True)],
            [],
        )
        self.assertNotIn("W", deps["R"])

    def test_two_write_nodes_are_independent(self):
        deps, _ = self._build(
            [_node("W1", fp_write=True), _node("W2", fp_write=True)],
            [],
        )
        self.assertNotIn("W1", deps["W2"])
        self.assertNotIn("W2", deps["W1"])

    def test_read_write_depends_on_prior_write(self):
        deps, _ = self._build(
            [_node("W", fp_write=True), _node("RW", fp_read=True, fp_write=True)],
            [],
        )
        self.assertIn("W", deps["RW"])

    def test_linear_chain_three_levels(self):
        _, levels = self._build(
            [
                _node("writer",  fp_write=True),
                _node("analyst", fp_read=True, fp_write=True),
                _node("reader",  fp_read=True),
            ],
            [],
        )
        self.assertLess(_level_of(levels, "writer"),  _level_of(levels, "analyst"))
        self.assertLess(_level_of(levels, "analyst"), _level_of(levels, "reader"))

    def test_plain_nodes_unaffected(self):
        deps, _ = self._build([_node("A"), _node("B")], [])
        self.assertEqual(deps["A"], set())
        self.assertEqual(deps["B"], set())

    def test_cat2_nodes_parallel_with_flat_edges(self):
        """Cat-2 enrichers (read+write) never depend on each other — they run in
        parallel after Cat-1 writers, even with flat edge declarations."""
        deps, levels = self._build(
            [
                _node("assistant", fp_write=True),
                _node("analyst_a", fp_read=True, fp_write=True),
                _node("analyst_b", fp_read=True, fp_write=True),
                _node("summarizer", fp_read=True),
            ],
            [],
        )
        # Cat-2 nodes must not depend on each other
        self.assertNotIn("analyst_a", deps["analyst_b"])
        self.assertNotIn("analyst_b", deps["analyst_a"])
        # both at the same level
        self.assertEqual(_level_of(levels, "analyst_a"), _level_of(levels, "analyst_b"))
        # topology: assistant < analysts < summarizer
        self.assertLess(_level_of(levels, "assistant"), _level_of(levels, "analyst_a"))
        self.assertLess(_level_of(levels, "analyst_a"), _level_of(levels, "summarizer"))


# ---------------------------------------------------------------------------
# Integration: footprint_graph.yml  (requires Ollama + ministral-3:3b)
# ---------------------------------------------------------------------------

class TestFootprintGraph(unittest.TestCase):
    graph_path     = CURRENT_DIR / "graphs" / "footprint_graph.yml"
    footprint_file = CURRENT_DIR / "graphs" / "FOOTPRINT.md"
    out_dir        = CURRENT_DIR / "graph_outputs" / "footprint_graph"
    _seed = "# Renewable Energy Discussion\n\n"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def _reset_and_recreate(self):
        """Reset FOOTPRINT.md to the seed and create a fresh compiler that reads it."""
        self.compiler.close()
        self.footprint_file.write_text(self._seed, encoding="utf-8")
        self.compiler = Compiler(uri=str(self.graph_path))

    def test_dag_levels(self):
        """assistant < {analyst_a, analyst_b in parallel} < summarizer."""
        deps   = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)
        # analysts are siblings — same level, no cross-dependency
        self.assertEqual(_level_of(levels, "analyst_a"), _level_of(levels, "analyst_b"))
        self.assertNotIn("analyst_a", deps["analyst_b"])
        self.assertNotIn("analyst_b", deps["analyst_a"])
        # assistant before analysts, analysts before summarizer
        self.assertLess(_level_of(levels, "assistant"), _level_of(levels, "analyst_a"))
        self.assertLess(_level_of(levels, "analyst_a"), _level_of(levels, "summarizer"))

    def test_compile(self):
        """All four nodes execute; FOOTPRINT.md grows beyond the seed."""
        self._reset_and_recreate()
        self.compiler.compile()
        executed_ids = {n.node_id for n in self.compiler.get_outputs().nodes}
        self.assertIn("assistant",  executed_ids)
        self.assertIn("analyst_a",  executed_ids)
        self.assertIn("analyst_b",  executed_ids)
        self.assertIn("summarizer", executed_ids)
        on_disk = self.footprint_file.read_text(encoding="utf-8")
        self.assertGreater(len(on_disk), len(self._seed))

    def test_compile_to_file(self):
        """Compile, write full output and summarizer-only markdown to graph_outputs/."""
        self._reset_and_recreate()
        self.compiler.compile()

        self.compiler.save_outputs_as_json(
            self.out_dir / "footprint_graph.json"
        )
        self.compiler.save_outputs_as_markdown(
            self.out_dir / "footprint_graph.md"
        )

        summarizer_response = next(
            n.response for n in self.compiler.get_outputs().nodes
            if n.node_id == "summarizer" and n.show
        )
        summarizer_md = "\n\n".join(summarizer_response.messages or [])
        out_path = self.out_dir / "summarizer_output.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(summarizer_md, encoding="utf-8")
