"""Tests for the multi-board blackboard pipeline element.

Structure:
  - Model unit tests      — NodeBlackboardRef, BlackboardEntry, GraphBlackboard
  - Graph parsing tests   — new multi-board blackboard format
  - _init_boards tests    — file creation, cleanup, no-cleanup
  - _assemble_board tests — import chain resolution
  - _update_blackboard    — writes to correct board, persists to file
  - New validation tests  — board-ID, tool, mcp_server, stdio checks
  - DAG inference tests   — blackboard write→read dependency inference
  - Integration tests     — blackboard_graph.yml (requires Ollama + ministral-3:3b)
"""

import tempfile
import threading
import unittest
from pathlib import Path
from kegal.compiler import Compiler
from kegal.graph import Graph, GraphMcpServer
from kegal.graph_blackboard import BlackboardEntry, GraphBlackboard, NodeBlackboardRef
from kegal.graph_node import GraphNode, NodePrompt

CURRENT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_compiler(nodes_cfg: list, edges_cfg: list) -> Compiler:
    """Build a lightweight Compiler from config dicts without connecting to any LLM."""
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
    c._board_entries = {}
    c._boards = {}
    c._board_paths = {}
    c._blackboard_lock = threading.Lock()
    c._blackboard_write_buffer = None
    return c


def _node(nid: str, bb_read: bool = False, bb_write: bool = False,
          bb_id: str = "main", bb_chain: bool = False) -> dict:
    n: dict = {
        "id": nid, "model": 0, "temperature": 0.0, "max_tokens": 10,
        "show": False,
        "message_passing": {"input": False, "output": False},
        "prompt": {"template": 0},
    }
    if bb_read or bb_write:
        n["blackboard"] = {
            "id": bb_id, "read": bb_read, "write": bb_write, "chain": bb_chain,
        }
    return n


def _level_of(levels: list, nid: str) -> int:
    return next(i for i, lvl in enumerate(levels) if nid in lvl)


def _bare_validate_compiler(nodes: dict, graph_mcp_servers=None,
                             tools=None, board_entries=None) -> Compiler:
    """Build a Compiler skeleton with just the attributes _validate_indices() needs."""
    c = object.__new__(Compiler)
    c.nodes = nodes
    c.edges = []
    c.clients = [object()]   # 1 client → model index 0 is valid
    c.prompts = [{}]         # 1 prompt → template index 0 is valid
    c.tools = tools
    c.graph_mcp_servers = graph_mcp_servers or []
    c._board_entries = board_entries or {}
    return c


# ---------------------------------------------------------------------------
# NodeBlackboardRef model
# ---------------------------------------------------------------------------

class TestNodeBlackboardRef(unittest.TestCase):

    def test_defaults(self):
        bb = NodeBlackboardRef(id="board1")
        self.assertEqual(bb.id, "board1")
        self.assertFalse(bb.read)
        self.assertFalse(bb.write)
        self.assertFalse(bb.chain)

    def test_chain_flag(self):
        bb = NodeBlackboardRef(id="x", read=True, write=True, chain=True)
        self.assertTrue(bb.chain)

    def test_read_only(self):
        bb = NodeBlackboardRef(id="x", read=True)
        self.assertTrue(bb.read)
        self.assertFalse(bb.write)

    def test_write_only(self):
        bb = NodeBlackboardRef(id="x", write=True)
        self.assertFalse(bb.read)
        self.assertTrue(bb.write)

    def test_both_true(self):
        bb = NodeBlackboardRef(id="x", read=True, write=True)
        self.assertTrue(bb.read)
        self.assertTrue(bb.write)


# ---------------------------------------------------------------------------
# BlackboardEntry model
# ---------------------------------------------------------------------------

class TestBlackboardEntry(unittest.TestCase):

    def test_defaults(self):
        e = BlackboardEntry(id="b1", file="b1.md")
        self.assertEqual(e.id, "b1")
        self.assertEqual(e.file, "b1.md")
        self.assertTrue(e.cleanup)
        self.assertEqual(e.imports, [])

    def test_cleanup_false(self):
        e = BlackboardEntry(id="b1", file="b1.md", cleanup=False)
        self.assertFalse(e.cleanup)

    def test_import_yaml_alias(self):
        """'import' YAML key (reserved word) maps to 'imports' Python attribute."""
        e = BlackboardEntry.model_validate({"id": "b2", "file": "b2.md", "import": ["b1"]})
        self.assertEqual(e.imports, ["b1"])


# ---------------------------------------------------------------------------
# GraphBlackboard model validation
# ---------------------------------------------------------------------------

class TestGraphBlackboard(unittest.TestCase):

    def test_valid_single_board(self):
        gb = GraphBlackboard(path="./boards/",
                             boards=[BlackboardEntry(id="main", file="main.md")])
        self.assertEqual(len(gb.boards), 1)

    def test_duplicate_board_id_raises(self):
        with self.assertRaises(Exception):
            GraphBlackboard(path="./", boards=[
                BlackboardEntry(id="x", file="x1.md"),
                BlackboardEntry(id="x", file="x2.md"),
            ])

    def test_import_unknown_board_raises(self):
        with self.assertRaises(Exception):
            GraphBlackboard.model_validate({
                "path": "./",
                "boards": [{"id": "b", "file": "b.md", "import": ["nonexistent"]}],
            })

    def test_valid_import_chain(self):
        gb = GraphBlackboard.model_validate({
            "path": "./",
            "boards": [
                {"id": "a", "file": "a.md"},
                {"id": "b", "file": "b.md", "import": ["a"]},
            ],
        })
        self.assertEqual(gb.boards[1].imports, ["a"])


# ---------------------------------------------------------------------------
# Graph YAML parsing
# ---------------------------------------------------------------------------

class TestGraphParsing(unittest.TestCase):

    def _source(self, blackboard=None, node_blackboard=None):
        node: dict = {
            "id": "n", "model": 0, "temperature": 0.0, "max_tokens": 10,
            "show": False, "message_passing": {"input": False, "output": False},
            "prompt": {"template": 0},
        }
        if node_blackboard:
            node["blackboard"] = node_blackboard
        src: dict = {
            "models": [{"llm": "ollama", "model": "dummy"}],
            "prompts": [{"template": {}}],
            "nodes": [node],
            "edges": [],
        }
        if blackboard is not None:
            src["blackboard"] = blackboard
        return src

    def test_blackboard_absent_is_none(self):
        self.assertIsNone(Graph.model_validate(self._source()).blackboard)

    def test_blackboard_object_parsed(self):
        graph = Graph.model_validate(self._source(
            blackboard={"path": "./", "boards": [{"id": "main", "file": "main.md"}]}
        ))
        self.assertIsInstance(graph.blackboard, GraphBlackboard)
        self.assertEqual(graph.blackboard.boards[0].id, "main")
        self.assertEqual(graph.blackboard.path, "./")

    def test_node_blackboard_parsed(self):
        graph = Graph.model_validate(self._source(
            blackboard={"path": "./", "boards": [{"id": "main", "file": "main.md"}]},
            node_blackboard={"id": "main", "read": True, "write": True},
        ))
        bb = graph.nodes[0].blackboard
        self.assertIsNotNone(bb)
        self.assertIsInstance(bb, NodeBlackboardRef)
        self.assertEqual(bb.id, "main")
        self.assertTrue(bb.read)
        self.assertTrue(bb.write)

    def test_node_without_blackboard_is_none(self):
        self.assertIsNone(Graph.model_validate(self._source()).nodes[0].blackboard)

    def test_duplicate_node_ids_raise(self):
        src = self._source()
        src["nodes"] = [
            {"id": "n", "model": 0, "temperature": 0.0, "max_tokens": 10, "show": False,
             "prompt": {"template": 0}},
            {"id": "n", "model": 0, "temperature": 0.0, "max_tokens": 10, "show": False,
             "prompt": {"template": 0}},
        ]
        with self.assertRaises(Exception):
            Graph.model_validate(src)


# ---------------------------------------------------------------------------
# _init_boards — file creation, cleanup semantics
# ---------------------------------------------------------------------------

class TestInitBoards(unittest.TestCase):

    def _run_init(self, board_cfgs: list[dict], tmpdir: Path) -> Compiler:
        c = object.__new__(Compiler)
        c._graph_dir = tmpdir
        c._board_entries = {}
        c._boards = {}
        c._board_paths = {}
        cfg = GraphBlackboard.model_validate({"path": "./", "boards": board_cfgs})
        c._init_boards(cfg)
        return c

    def test_cleanup_truncates_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            (tmpdir / "b.md").write_text("old content", encoding="utf-8")
            c = self._run_init([{"id": "b", "file": "b.md", "cleanup": True}], tmpdir)
            self.assertEqual(c._boards["b"], "")
            self.assertEqual((tmpdir / "b.md").read_text(encoding="utf-8"), "")

    def test_cleanup_creates_file_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            c = self._run_init([{"id": "x", "file": "x.md"}], tmpdir)
            self.assertTrue((tmpdir / "x.md").exists())
            self.assertEqual(c._boards["x"], "")

    def test_no_cleanup_loads_existing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            (tmpdir / "b.md").write_text("# Seed content", encoding="utf-8")
            c = self._run_init([{"id": "b", "file": "b.md", "cleanup": False}], tmpdir)
            self.assertEqual(c._boards["b"], "# Seed content")

    def test_no_cleanup_empty_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            c = self._run_init([{"id": "b", "file": "b.md", "cleanup": False}], tmpdir)
            self.assertEqual(c._boards["b"], "")

    def test_multiple_boards_all_initialised(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            c = self._run_init([
                {"id": "a", "file": "a.md"},
                {"id": "b", "file": "b.md"},
            ], tmpdir)
            self.assertIn("a", c._board_entries)
            self.assertIn("b", c._board_entries)
            self.assertIn("a", c._boards)
            self.assertIn("b", c._boards)


# ---------------------------------------------------------------------------
# _assemble_board — import chain resolution
# ---------------------------------------------------------------------------

class TestAssembleBoard(unittest.TestCase):

    def _compiler(self, entry_imports: dict[str, list[str]],
                  boards: dict[str, str]) -> Compiler:
        """Build a minimal Compiler with _board_entries and _boards populated."""
        c = object.__new__(Compiler)
        c._board_entries = {
            bid: BlackboardEntry.model_validate(
                {"id": bid, "file": f"{bid}.md", "import": imports}
            )
            for bid, imports in entry_imports.items()
        }
        c._boards = boards
        return c

    def test_simple_board_no_imports(self):
        c = self._compiler({"main": []}, {"main": "Hello world"})
        self.assertEqual(c._assemble_board("main"), "Hello world")

    def test_single_import_prepended(self):
        c = self._compiler(
            {"a": [], "b": ["a"]},
            {"a": "A content", "b": "B content"},
        )
        result = c._assemble_board("b")
        self.assertIn("A content", result)
        self.assertIn("B content", result)
        self.assertLess(result.index("A content"), result.index("B content"))

    def test_multiple_imports_in_declaration_order(self):
        c = self._compiler(
            {"a": [], "b": [], "c": ["a", "b"]},
            {"a": "AAA", "b": "BBB", "c": "CCC"},
        )
        result = c._assemble_board("c")
        self.assertLess(result.index("AAA"), result.index("BBB"))
        self.assertLess(result.index("BBB"), result.index("CCC"))

    def test_unknown_board_returns_empty(self):
        c = self._compiler({}, {})
        self.assertEqual(c._assemble_board("nonexistent"), "")

    def test_empty_board_content_excluded(self):
        """Board entries with empty string content are not included in the result."""
        c = self._compiler(
            {"a": [], "b": ["a"]},
            {"a": "", "b": "actual content"},
        )
        self.assertEqual(c._assemble_board("b"), "actual content")


# ---------------------------------------------------------------------------
# _update_blackboard — writes to the correct board, persists to file
# ---------------------------------------------------------------------------

class TestUpdateBlackboard(unittest.TestCase):

    def _setup(self, tmpdir: Path) -> tuple[Compiler, Path]:
        board_path = tmpdir / "main.md"
        board_path.write_text("", encoding="utf-8")
        c = object.__new__(Compiler)
        c._board_entries = {"main": BlackboardEntry(id="main", file="main.md")}
        c._boards = {"main": ""}
        c._board_paths = {"main": board_path}
        c._blackboard_lock = threading.Lock()
        c._blackboard_write_buffer = None
        return c, board_path

    def _response(self, text: str):
        from kegal.llm.llm_model import LLmResponse
        r = LLmResponse()
        r.messages = [text]
        return r

    def _node_bb(self, write: bool, read: bool = False) -> GraphNode:
        return GraphNode(
            id="n", model=0, temperature=0.0, max_tokens=10, show=False,
            prompt=None,
            blackboard=NodeBlackboardRef(id="main", read=read, write=write),
        )

    def test_first_write_sets_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, _ = self._setup(Path(tmp))
            c._update_blackboard(self._node_bb(write=True), self._response("First"))
            self.assertEqual(c._boards["main"], "First")

    def test_second_write_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, _ = self._setup(Path(tmp))
            c._update_blackboard(self._node_bb(write=True), self._response("First"))
            c._update_blackboard(self._node_bb(write=True), self._response("Second"))
            self.assertIn("First", c._boards["main"])
            self.assertIn("Second", c._boards["main"])

    def test_write_persists_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, board_path = self._setup(Path(tmp))
            c._update_blackboard(self._node_bb(write=True), self._response("persisted"))
            self.assertEqual(board_path.read_text(encoding="utf-8"), c._boards["main"])

    def test_write_false_does_not_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, _ = self._setup(Path(tmp))
            node = GraphNode(
                id="n", model=0, temperature=0.0, max_tokens=10, show=False,
                prompt=None,
                blackboard=NodeBlackboardRef(id="main", read=True, write=False),
            )
            c._update_blackboard(node, self._response("ignored"))
            self.assertEqual(c._boards["main"], "")

    def test_no_blackboard_on_node_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, _ = self._setup(Path(tmp))
            node = GraphNode(id="n", model=0, temperature=0.0, max_tokens=10,
                             show=False, prompt=None)
            c._update_blackboard(node, self._response("ignored"))
            self.assertEqual(c._boards["main"], "")


# ---------------------------------------------------------------------------
# New _validate_indices checks — board IDs, tool refs, mcp_server refs, stdio
# ---------------------------------------------------------------------------

class TestNewValidations(unittest.TestCase):

    def _node(self, nid="n", **overrides) -> GraphNode:
        defaults = dict(id=nid, model=0, temperature=0.0, max_tokens=10,
                        show=False, prompt=NodePrompt(template=0))
        defaults.update(overrides)
        return GraphNode(**defaults)

    def test_unknown_board_id_raises(self):
        """node.blackboard.id not in graph.blackboard.boards → error."""
        node = self._node(blackboard=NodeBlackboardRef(id="ghost", read=True))
        c = _bare_validate_compiler(
            nodes={"n": node},
            board_entries={"main": BlackboardEntry(id="main", file="main.md")},
        )
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("ghost", str(ctx.exception))

    def test_known_board_id_passes(self):
        node = self._node(blackboard=NodeBlackboardRef(id="main", write=True))
        c = _bare_validate_compiler(
            nodes={"n": node},
            board_entries={"main": BlackboardEntry(id="main", file="main.md")},
        )
        c._validate_indices()  # must not raise

    def test_unknown_tool_ref_raises(self):
        """node.tools contains a name not in graph.tools → error."""
        node = self._node(tools=["ghost_tool"])
        c = _bare_validate_compiler(nodes={"n": node}, tools=[])
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("ghost_tool", str(ctx.exception))

    def test_unknown_mcp_server_ref_raises(self):
        """node.mcp_servers contains an ID not in graph.mcp_servers → error."""
        node = self._node(mcp_servers=["ghost_srv"])
        c = _bare_validate_compiler(nodes={"n": node}, graph_mcp_servers=[])
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("ghost_srv", str(ctx.exception))

    def test_stdio_mcp_without_command_raises(self):
        """MCP server with transport=stdio but no command → error."""
        c = _bare_validate_compiler(
            nodes={},
            graph_mcp_servers=[GraphMcpServer(id="s", transport="stdio")],
        )
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("stdio", str(ctx.exception))

    def test_stdio_mcp_with_command_passes(self):
        """MCP server with transport=stdio and a command → no error."""
        c = _bare_validate_compiler(
            nodes={},
            graph_mcp_servers=[GraphMcpServer(id="s", transport="stdio",
                                              command="python", args=[])],
        )
        c._validate_indices()  # must not raise

    def test_multiple_errors_reported_together(self):
        """All validation errors are collected into a single ValueError."""
        node_a = self._node("a", blackboard=NodeBlackboardRef(id="missing_board", read=True))
        node_b = self._node("b", tools=["missing_tool"])
        c = _bare_validate_compiler(
            nodes={"a": node_a, "b": node_b},
            tools=[],
            board_entries={},
        )
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        msg = str(ctx.exception)
        self.assertIn("missing_board", msg)
        self.assertIn("missing_tool", msg)


# ---------------------------------------------------------------------------
# DAG stage-4: blackboard write→read inference (no LLM)
# ---------------------------------------------------------------------------

class TestBlackboardDagInference(unittest.TestCase):

    def _build(self, nodes, edges):
        c = _make_compiler(nodes, edges)
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        return deps, levels

    def test_read_depends_on_prior_write(self):
        deps, _ = self._build(
            [_node("W", bb_write=True), _node("R", bb_read=True)], [],
        )
        self.assertIn("W", deps["R"])

    def test_read_before_write_no_dep(self):
        deps, _ = self._build(
            [_node("R", bb_read=True), _node("W", bb_write=True)], [],
        )
        self.assertNotIn("W", deps["R"])

    def test_two_write_nodes_are_independent(self):
        deps, _ = self._build(
            [_node("W1", bb_write=True), _node("W2", bb_write=True)], [],
        )
        self.assertNotIn("W1", deps["W2"])
        self.assertNotIn("W2", deps["W1"])

    def test_read_write_depends_on_prior_write(self):
        deps, _ = self._build(
            [_node("W", bb_write=True), _node("RW", bb_read=True, bb_write=True)], [],
        )
        self.assertIn("W", deps["RW"])

    def test_linear_chain_three_levels(self):
        _, levels = self._build([
            _node("writer",  bb_write=True),
            _node("analyst", bb_read=True, bb_write=True),
            _node("reader",  bb_read=True),
        ], [])
        self.assertLess(_level_of(levels, "writer"),  _level_of(levels, "analyst"))
        self.assertLess(_level_of(levels, "analyst"), _level_of(levels, "reader"))

    def test_plain_nodes_unaffected(self):
        deps, _ = self._build([_node("A"), _node("B")], [])
        self.assertEqual(deps["A"], set())
        self.assertEqual(deps["B"], set())

    def test_cat2_nodes_run_in_parallel(self):
        """Cat-2 enrichers (read+write) never depend on each other — parallel after Cat-1."""
        deps, levels = self._build([
            _node("assistant",  bb_write=True),
            _node("analyst_a",  bb_read=True, bb_write=True),
            _node("analyst_b",  bb_read=True, bb_write=True),
            _node("summarizer", bb_read=True),
        ], [])
        self.assertNotIn("analyst_a", deps["analyst_b"])
        self.assertNotIn("analyst_b", deps["analyst_a"])
        self.assertEqual(_level_of(levels, "analyst_a"), _level_of(levels, "analyst_b"))
        self.assertLess(_level_of(levels, "assistant"), _level_of(levels, "analyst_a"))
        self.assertLess(_level_of(levels, "analyst_a"), _level_of(levels, "summarizer"))


# ---------------------------------------------------------------------------
# DAG stage-4: Cat-2 sequential chains (blackboard.chain=True)
# ---------------------------------------------------------------------------

class TestBlackboardChainDagInference(unittest.TestCase):

    def _build(self, nodes, edges):
        c = _make_compiler(nodes, edges)
        deps = c._build_dag()
        levels = c._topological_levels(deps)
        return deps, levels

    def test_three_chained_nodes_form_a_sequential_chain(self):
        """3 Cat-2 nodes with chain=True on the same board:
        - first depends on prior Cat-1 (like today), not on siblings
        - second depends only on the first
        - third depends only on the second (NOT on the first)
        """
        deps, levels = self._build([
            _node("seed", bb_write=True),
            _node("c1", bb_read=True, bb_write=True, bb_chain=True),
            _node("c2", bb_read=True, bb_write=True, bb_chain=True),
            _node("c3", bb_read=True, bb_write=True, bb_chain=True),
        ], [])

        # first chained node: same Cat-1 dependency as an unchained Cat-2 node
        self.assertIn("seed", deps["c1"])
        self.assertNotIn("c2", deps["c1"])
        self.assertNotIn("c3", deps["c1"])

        # second depends on first only
        self.assertEqual(deps["c2"], {"c1"})

        # third depends on second only — crucially NOT on the first
        self.assertEqual(deps["c3"], {"c2"})
        self.assertNotIn("c1", deps["c3"])
        self.assertNotIn("seed", deps["c3"])

        # topological consequence: strictly increasing levels
        self.assertLess(_level_of(levels, "seed"), _level_of(levels, "c1"))
        self.assertLess(_level_of(levels, "c1"), _level_of(levels, "c2"))
        self.assertLess(_level_of(levels, "c2"), _level_of(levels, "c3"))

    def test_chains_on_different_boards_are_independent(self):
        """Chained nodes on board 'A' and board 'B' must not depend on each
        other — each board keeps its own chain."""
        deps, levels = self._build([
            _node("seed_a", bb_write=True, bb_id="A"),
            _node("seed_b", bb_write=True, bb_id="B"),
            _node("a1", bb_read=True, bb_write=True, bb_id="A", bb_chain=True),
            _node("b1", bb_read=True, bb_write=True, bb_id="B", bb_chain=True),
            _node("a2", bb_read=True, bb_write=True, bb_id="A", bb_chain=True),
            _node("b2", bb_read=True, bb_write=True, bb_id="B", bb_chain=True),
        ], [])

        # chain A: a1 -> a2, no coupling to board B's chain
        self.assertEqual(deps["a2"], {"a1"})
        self.assertNotIn("b1", deps["a2"])
        self.assertNotIn("b2", deps["a2"])

        # chain B: b1 -> b2, no coupling to board A's chain
        self.assertEqual(deps["b2"], {"b1"})
        self.assertNotIn("a1", deps["b2"])
        self.assertNotIn("a2", deps["b2"])

        # first node of each chain keeps the legacy Cat-1 dependency (all prior
        # writers) but never depends on the other board's chain nodes
        self.assertIn("seed_a", deps["a1"])
        self.assertIn("seed_b", deps["b1"])
        self.assertNotIn("b1", deps["a1"])
        self.assertNotIn("b2", deps["a1"])
        self.assertNotIn("a1", deps["b1"])
        self.assertNotIn("a2", deps["b1"])

        # the two chains can advance in parallel — a1/b1 share a level, a2/b2 share a level
        self.assertEqual(_level_of(levels, "a1"), _level_of(levels, "b1"))
        self.assertEqual(_level_of(levels, "a2"), _level_of(levels, "b2"))

    def test_chained_and_unchained_on_same_board_do_not_interfere(self):
        """Some Cat-2 nodes chain=True, others chain=False on the same board:
        - unchained nodes keep the old behaviour (parallel, depend on Cat-1 only)
        - chained nodes form their own sequential chain
        - the two groups do not depend on each other
        """
        deps, levels = self._build([
            _node("seed", bb_write=True),
            _node("free_a", bb_read=True, bb_write=True),                 # unchained
            _node("ch_1",  bb_read=True, bb_write=True, bb_chain=True),   # chained
            _node("free_b", bb_read=True, bb_write=True),                 # unchained
            _node("ch_2",  bb_read=True, bb_write=True, bb_chain=True),   # chained
        ], [])

        # unchained group: depends on Cat-1 only, never on siblings or chain nodes
        self.assertEqual(deps["free_a"], {"seed"})
        self.assertEqual(deps["free_b"], {"seed"})
        self.assertNotIn("free_a", deps["free_b"])
        self.assertNotIn("ch_1", deps["free_b"])
        self.assertNotIn("ch_2", deps["free_b"])

        # chained group: ch_1 depends on Cat-1, ch_2 depends on ch_1 only
        self.assertEqual(deps["ch_1"], {"seed"})
        self.assertEqual(deps["ch_2"], {"ch_1"})
        self.assertNotIn("free_a", deps["ch_2"])
        self.assertNotIn("free_b", deps["ch_2"])

        # unchained nodes and the first chain node share a level (all wait on seed only)
        self.assertEqual(_level_of(levels, "free_a"), _level_of(levels, "ch_1"))
        self.assertEqual(_level_of(levels, "free_b"), _level_of(levels, "ch_1"))
        # the rest of the chain comes strictly later
        self.assertLess(_level_of(levels, "ch_1"), _level_of(levels, "ch_2"))

    def test_chain_false_is_bit_for_bit_identical_to_legacy(self):
        """With chain omitted/False the inferred deps must match the pre-chain
        behaviour exactly (regression guard for backward compatibility)."""
        nodes = [
            _node("seed", bb_write=True),
            _node("e_a", bb_read=True, bb_write=True),
            _node("e_b", bb_read=True, bb_write=True),
            _node("final", bb_read=True),
        ]
        deps, _ = self._build(nodes, [])
        self.assertEqual(deps["e_a"], {"seed"})
        self.assertEqual(deps["e_b"], {"seed"})
        self.assertEqual(deps["final"], {"seed", "e_a", "e_b"})


# ---------------------------------------------------------------------------
# Integration: blackboard_graph.yml  (requires Ollama + ministral-3:3b)
# ---------------------------------------------------------------------------

class TestBlackboardGraph(unittest.TestCase):
    graph_path      = CURRENT_DIR / "graphs" / "blackboard_graph.yml"
    blackboard_file = CURRENT_DIR / "graphs" / "BLACKBOARD.md"
    out_dir         = CURRENT_DIR / "graph_outputs" / "blackboard_graph"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_dag_levels(self):
        """assistant < {analyst_a, analyst_b in parallel} < summarizer."""
        deps   = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)
        self.assertEqual(_level_of(levels, "analyst_a"), _level_of(levels, "analyst_b"))
        self.assertNotIn("analyst_a", deps["analyst_b"])
        self.assertNotIn("analyst_b", deps["analyst_a"])
        self.assertLess(_level_of(levels, "assistant"), _level_of(levels, "analyst_a"))
        self.assertLess(_level_of(levels, "analyst_a"), _level_of(levels, "summarizer"))

    def test_board_initialised_at_init(self):
        """Compiler init must have created the board file and populated board state."""
        self.assertIn("main", self.compiler._board_entries)
        self.assertIn("main", self.compiler._boards)
        self.assertIn("main", self.compiler._board_paths)
        self.assertTrue(self.compiler._board_paths["main"].exists())

    def test_compile(self):
        """All four nodes execute and the blackboard file grows after compilation."""
        self.compiler.compile()
        executed_ids = {n.node_id for n in self.compiler.get_outputs().nodes}
        self.assertIn("assistant",  executed_ids)
        self.assertIn("analyst_a",  executed_ids)
        self.assertIn("analyst_b",  executed_ids)
        self.assertIn("summarizer", executed_ids)
        on_disk = self.blackboard_file.read_text(encoding="utf-8")
        self.assertGreater(len(on_disk), 0)

    def test_compile_to_file(self):
        """Compile and write full output + summarizer-only markdown."""
        self.compiler.compile()
        self.compiler.save_outputs_as_json(self.out_dir / "blackboard_graph.json")
        self.compiler.save_outputs_as_markdown(self.out_dir / "blackboard_graph.md")
        summarizer_response = next(
            n.response for n in self.compiler.get_outputs().nodes
            if n.node_id == "summarizer" and n.show
        )
        summarizer_md = "\n\n".join(summarizer_response.messages or [])
        out_path = self.out_dir / "summarizer_output.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(summarizer_md, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
