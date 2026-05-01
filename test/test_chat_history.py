"""Tests for ChatHistoryFile and file-based chat history scopes.

Structure:
  - ChatHistoryFile model unit tests
  - Graph parsing — inline arrays, ChatHistoryFile entries, mixed
  - _init_history — inline array, file-based (file exists / missing), auto flag, URL
  - _update_auto_history — writes user+assistant turns, persists to file
  - _chat_history_check — guard logic
  - _validate_indices — scope uniqueness
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kegal.compiler import Compiler, CompiledOutput, CompiledNodeOutput
from kegal.graph import Graph
from kegal.graph_history import ChatHistoryFile
from kegal.graph_node import GraphNode, NodePrompt
from kegal.llm.llm_model import LLmResponse


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_node(nid: str, ch_key: str | None = None) -> GraphNode:
    prompt = NodePrompt(template=0, chat_history=ch_key) if ch_key else NodePrompt(template=0)
    return GraphNode(id=nid, model=0, temperature=0.0, max_tokens=10,
                     show=True, prompt=prompt)


def _response(text: str) -> LLmResponse:
    r = LLmResponse()
    r.messages = [text]
    return r


def _base_source(**overrides) -> dict:
    src: dict = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": [{"id": "n", "model": 0, "temperature": 0.0, "max_tokens": 10,
                   "show": False, "prompt": {"template": 0}}],
        "edges": [],
    }
    src.update(overrides)
    return src


def _make_init_compiler(graph_dir: Path) -> Compiler:
    c = object.__new__(Compiler)
    c._graph_dir = graph_dir
    c.chat_history = {}
    c._history_auto_paths = {}
    return c


def _make_update_compiler(
    graph_dir: Path,
    nodes: list[GraphNode],
    history: dict,
    auto_paths: dict[str, Path],
    node_outputs: list[tuple[str, LLmResponse]],
    user_message: str | None = None,
) -> Compiler:
    c = object.__new__(Compiler)
    c._graph_dir = graph_dir
    c.nodes = {n.id: n for n in nodes}
    c.chat_history = history
    c._history_auto_paths = auto_paths
    c.user_message = user_message
    out = CompiledOutput()
    for nid, resp in node_outputs:
        node = next(n for n in nodes if n.id == nid)
        out.nodes.append(CompiledNodeOutput(
            node_id=nid, response=resp, compiled_time=0.0,
            show=node.show, history=True,
        ))
    c.outputs = out
    return c


def _minimal_compiler(nodes: dict, chat_history: dict | None = None) -> Compiler:
    c = object.__new__(Compiler)
    c.nodes = nodes
    c.edges = []
    c.clients = [object()]
    c.prompts = [{}]
    c.tools = None
    c.graph_mcp_servers = []
    c._board_entries = {}
    c.chat_history = chat_history or {}
    c._history_auto_paths = {}
    return c


# ---------------------------------------------------------------------------
# ChatHistoryFile model
# ---------------------------------------------------------------------------

class TestChatHistoryFile(unittest.TestCase):

    def test_defaults(self):
        f = ChatHistoryFile(path="chat.json")
        self.assertEqual(f.path, "chat.json")
        self.assertFalse(f.auto)

    def test_auto_true(self):
        f = ChatHistoryFile(path="chat.json", auto=True)
        self.assertTrue(f.auto)

    def test_model_validate_from_dict(self):
        f = ChatHistoryFile.model_validate({"path": "sessions/a.json", "auto": True})
        self.assertEqual(f.path, "sessions/a.json")
        self.assertTrue(f.auto)

    def test_path_required(self):
        with self.assertRaises(Exception):
            ChatHistoryFile.model_validate({"auto": True})


# ---------------------------------------------------------------------------
# Graph parsing — chat_history field
# ---------------------------------------------------------------------------

class TestChatHistoryGraphParsing(unittest.TestCase):

    def test_chat_history_absent_is_none(self):
        g = Graph.model_validate(_base_source())
        self.assertIsNone(g.chat_history)

    def test_chat_history_inline_array(self):
        g = Graph.model_validate(_base_source(chat_history={
            "session_a": [{"role": "user", "content": "hi"}]
        }))
        self.assertIsNotNone(g.chat_history)
        scope = g.chat_history["session_a"]
        self.assertIsInstance(scope, list)
        self.assertEqual(scope[0]["role"], "user")

    def test_chat_history_file_parsed(self):
        g = Graph.model_validate(_base_source(chat_history={
            "session_b": {"path": "history/b.json", "auto": True}
        }))
        scope = g.chat_history["session_b"]
        self.assertIsInstance(scope, ChatHistoryFile)
        self.assertEqual(scope.path, "history/b.json")
        self.assertTrue(scope.auto)

    def test_chat_history_mixed_scopes(self):
        g = Graph.model_validate(_base_source(chat_history={
            "inline": [{"role": "assistant", "content": "Hello"}],
            "file_scope": {"path": "f.json", "auto": False},
        }))
        self.assertIsInstance(g.chat_history["inline"], list)
        self.assertIsInstance(g.chat_history["file_scope"], ChatHistoryFile)

    def test_chat_history_file_auto_false_default(self):
        g = Graph.model_validate(_base_source(chat_history={
            "s": {"path": "x.json"}
        }))
        scope = g.chat_history["s"]
        self.assertIsInstance(scope, ChatHistoryFile)
        self.assertFalse(scope.auto)


# ---------------------------------------------------------------------------
# _init_history — resolve scopes at Compiler init time
# ---------------------------------------------------------------------------

class TestInitHistory(unittest.TestCase):

    def test_inline_array_stored_as_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _make_init_compiler(Path(tmp))
            msgs = [{"role": "user", "content": "hello"}]
            c._init_history({"s": msgs})
            self.assertEqual(c.chat_history["s"], msgs)
            self.assertNotIn("s", c._history_auto_paths)

    def test_file_scope_loads_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history = [{"role": "assistant", "content": "Hi there"}]
            (tmpdir / "chat.json").write_text(
                json.dumps(history), encoding="utf-8"
            )
            c = _make_init_compiler(tmpdir)
            c._init_history({"s": ChatHistoryFile(path="chat.json")})
            self.assertEqual(c.chat_history["s"], history)

    def test_file_scope_missing_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _make_init_compiler(Path(tmp))
            c._init_history({"s": ChatHistoryFile(path="nonexistent.json")})
            self.assertEqual(c.chat_history["s"], [])

    def test_auto_scope_registers_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            c = _make_init_compiler(tmpdir)
            c._init_history({"s": ChatHistoryFile(path="chat.json", auto=True)})
            self.assertIn("s", c._history_auto_paths)
            self.assertEqual(c._history_auto_paths["s"], tmpdir / "chat.json")

    def test_non_auto_file_scope_not_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _make_init_compiler(Path(tmp))
            c._init_history({"s": ChatHistoryFile(path="chat.json", auto=False)})
            self.assertNotIn("s", c._history_auto_paths)

    def test_inline_scope_never_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _make_init_compiler(Path(tmp))
            c._init_history({"s": [{"role": "user", "content": "q"}]})
            self.assertNotIn("s", c._history_auto_paths)

    def test_multiple_scopes_mixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            history_b = [{"role": "user", "content": "Q"}]
            (tmpdir / "b.json").write_text(json.dumps(history_b), encoding="utf-8")
            c = _make_init_compiler(tmpdir)
            c._init_history({
                "inline": [{"role": "user", "content": "direct"}],
                "file_auto": ChatHistoryFile(path="b.json", auto=True),
            })
            self.assertEqual(c.chat_history["inline"], [{"role": "user", "content": "direct"}])
            self.assertEqual(c.chat_history["file_auto"], history_b)
            self.assertIn("file_auto", c._history_auto_paths)
            self.assertNotIn("inline", c._history_auto_paths)

    def test_url_scope_downloads_json(self):
        remote = [{"role": "user", "content": "from server"}]
        with tempfile.TemporaryDirectory() as tmp:
            c = _make_init_compiler(Path(tmp))
            with patch("kegal.compiler.load_text_from_source",
                       return_value=json.dumps(remote)) as mock_load:
                c._init_history({"s": ChatHistoryFile(path="https://example.com/chat.json")})
                mock_load.assert_called_once_with("https://example.com/chat.json")
            self.assertEqual(c.chat_history["s"], remote)
            self.assertNotIn("s", c._history_auto_paths)

    def test_url_scope_with_auto_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _make_init_compiler(Path(tmp))
            with self.assertRaises(ValueError) as ctx:
                c._init_history({"s": ChatHistoryFile(path="https://example.com/chat.json", auto=True)})
            self.assertIn("auto", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# _update_auto_history — writes user+assistant turns, persists to file
# ---------------------------------------------------------------------------

class TestUpdateAutoHistory(unittest.TestCase):

    def test_no_auto_paths_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = _make_update_compiler(
                Path(tmp), nodes=[], history={}, auto_paths={},
                node_outputs=[],
            )
            c._update_auto_history()   # must not raise or write anything

    def test_appends_user_and_assistant_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            file_path = tmpdir / "chat.json"
            node = _make_node("responder", ch_key="session")
            c = _make_update_compiler(
                tmpdir,
                nodes=[node],
                history={"session": []},
                auto_paths={"session": file_path},
                node_outputs=[("responder", _response("I am the answer"))],
                user_message="What is the answer?",
            )
            c._update_auto_history()
            saved = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[0]["role"], "user")
            self.assertEqual(saved[0]["content"], "What is the answer?")
            self.assertEqual(saved[1]["role"], "assistant")
            self.assertEqual(saved[1]["content"], "I am the answer")

    def test_no_user_message_skips_user_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            file_path = tmpdir / "chat.json"
            node = _make_node("responder", ch_key="session")
            c = _make_update_compiler(
                tmpdir,
                nodes=[node],
                history={"session": []},
                auto_paths={"session": file_path},
                node_outputs=[("responder", _response("Only assistant"))],
                user_message=None,
            )
            c._update_auto_history()
            saved = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["role"], "assistant")
            self.assertEqual(saved[0]["content"], "Only assistant")

    def test_appends_to_existing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            file_path = tmpdir / "chat.json"
            existing = [
                {"role": "user", "content": "old question"},
                {"role": "assistant", "content": "old reply"},
            ]
            node = _make_node("responder", ch_key="session")
            c = _make_update_compiler(
                tmpdir,
                nodes=[node],
                history={"session": list(existing)},
                auto_paths={"session": file_path},
                node_outputs=[("responder", _response("new reply"))],
                user_message="new question",
            )
            c._update_auto_history()
            saved = json.loads(file_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved), 4)
            self.assertEqual(saved[0]["content"], "old question")
            self.assertEqual(saved[1]["content"], "old reply")
            self.assertEqual(saved[2]["content"], "new question")
            self.assertEqual(saved[3]["content"], "new reply")

    def test_in_memory_history_updated_too(self):
        """chat_history dict is updated in memory, not only on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            file_path = tmpdir / "chat.json"
            node = _make_node("responder", ch_key="s")
            c = _make_update_compiler(
                tmpdir,
                nodes=[node],
                history={"s": []},
                auto_paths={"s": file_path},
                node_outputs=[("responder", _response("hello"))],
                user_message="hi",
            )
            c._update_auto_history()
            self.assertEqual(len(c.chat_history["s"]), 2)

    def test_scope_with_no_matching_node_is_skipped(self):
        """Auto scope whose node has no matching prompt.chat_history does not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            file_path = tmpdir / "orphan.json"
            c = _make_update_compiler(
                tmpdir,
                nodes=[_make_node("unrelated")],  # no ch_key → no scope reference
                history={"orphan": []},
                auto_paths={"orphan": file_path},
                node_outputs=[("unrelated", _response("irrelevant"))],
                user_message=None,
            )
            c._update_auto_history()
            self.assertFalse(file_path.exists())

    def test_scope_with_no_output_node_is_skipped(self):
        """Node references scope but produced no output (not in outputs.nodes)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            file_path = tmpdir / "chat.json"
            node = _make_node("responder", ch_key="s")
            c = _make_update_compiler(
                tmpdir,
                nodes=[node],
                history={"s": []},
                auto_paths={"s": file_path},
                node_outputs=[],   # no output recorded for "responder"
                user_message="hi",
            )
            c._update_auto_history()
            self.assertFalse(file_path.exists())

    def test_creates_parent_dirs_if_needed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            file_path = tmpdir / "nested" / "dir" / "chat.json"
            node = _make_node("responder", ch_key="s")
            c = _make_update_compiler(
                tmpdir,
                nodes=[node],
                history={"s": []},
                auto_paths={"s": file_path},
                node_outputs=[("responder", _response("hi"))],
                user_message=None,
            )
            c._update_auto_history()
            self.assertTrue(file_path.exists())


# ---------------------------------------------------------------------------
# _chat_history_check
# ---------------------------------------------------------------------------

class TestChatHistoryCheck(unittest.TestCase):

    def _make(self, history: dict | None = None) -> Compiler:
        c = object.__new__(Compiler)
        c.chat_history = history if history is not None else {}
        return c

    def test_no_prompt_returns_false(self):
        c = self._make()
        node = GraphNode(id="n", model=0, temperature=0.0, max_tokens=10,
                         show=False, prompt=None)
        self.assertFalse(c._chat_history_check(node))

    def test_no_chat_history_key_on_prompt_returns_false(self):
        c = self._make()
        node = _make_node("n")   # prompt exists, chat_history key is None
        self.assertFalse(c._chat_history_check(node))

    def test_key_not_in_history_returns_false_and_warns(self):
        c = self._make(history={})
        node = _make_node("n", ch_key="missing")
        with self.assertLogs(level="WARNING"):
            result = c._chat_history_check(node)
        self.assertFalse(result)

    def test_key_present_returns_true(self):
        c = self._make(history={"s": []})
        node = _make_node("n", ch_key="s")
        self.assertTrue(c._chat_history_check(node))

    def test_key_present_with_messages_returns_true(self):
        c = self._make(history={"s": [{"role": "user", "content": "hi"}]})
        node = _make_node("n", ch_key="s")
        self.assertTrue(c._chat_history_check(node))


# ---------------------------------------------------------------------------
# _validate_indices — scope uniqueness enforcement
# ---------------------------------------------------------------------------

class TestChatHistoryScopeValidation(unittest.TestCase):

    def _node(self, nid: str, ch_key: str | None = None) -> GraphNode:
        prompt = NodePrompt(template=0, chat_history=ch_key)
        return GraphNode(id=nid, model=0, temperature=0.0, max_tokens=10,
                         show=False, prompt=prompt)

    def test_two_nodes_same_scope_raises(self):
        node_a = self._node("a", "shared")
        node_b = self._node("b", "shared")
        c = _minimal_compiler({"a": node_a, "b": node_b})
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        msg = str(ctx.exception)
        self.assertIn("shared", msg)

    def test_error_message_names_both_nodes(self):
        node_a = self._node("alpha", "dup")
        node_b = self._node("beta", "dup")
        c = _minimal_compiler({"alpha": node_a, "beta": node_b})
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        msg = str(ctx.exception)
        # Both node IDs must be mentioned
        self.assertTrue("alpha" in msg or "beta" in msg)

    def test_unique_scopes_pass(self):
        node_a = self._node("a", "scope_a")
        node_b = self._node("b", "scope_b")
        c = _minimal_compiler({"a": node_a, "b": node_b})
        c._validate_indices()   # must not raise

    def test_no_scope_passes(self):
        node_a = self._node("a")   # no chat_history key
        c = _minimal_compiler({"a": node_a})
        c._validate_indices()   # must not raise

    def test_single_node_with_scope_passes(self):
        node_a = self._node("a", "s")
        c = _minimal_compiler({"a": node_a})
        c._validate_indices()   # must not raise

    def test_duplicate_scope_included_in_multi_error_report(self):
        """Scope duplicate is collected alongside other errors in one ValueError."""
        node_a = self._node("a", "dup")
        node_b = self._node("b", "dup")
        # Also give node_b an invalid model index to produce two errors
        node_b_bad = GraphNode(id="b", model=99, temperature=0.0, max_tokens=10,
                               show=False, prompt=NodePrompt(template=0, chat_history="dup"))
        c = _minimal_compiler({"a": node_a, "b": node_b_bad})
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        msg = str(ctx.exception)
        self.assertIn("dup", msg)


# ---------------------------------------------------------------------------
# add_chat_history
# ---------------------------------------------------------------------------

def _bare_compiler() -> Compiler:
    c = object.__new__(Compiler)
    c.chat_history = {}
    c.retrieved_chunks = None
    return c


class TestAddChatHistory(unittest.TestCase):

    def test_inline_history(self):
        c = _bare_compiler()
        msgs = [{"role": "user", "content": "hi"}]
        c.add_chat_history("s", history=msgs)
        self.assertEqual(c.chat_history["s"], msgs)

    def test_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h.json"
            msgs = [{"role": "assistant", "content": "hello"}]
            path.write_text(json.dumps(msgs), encoding="utf-8")
            c = _bare_compiler()
            c.add_chat_history("s", file=path)
            self.assertEqual(c.chat_history["s"], msgs)

    def test_from_uri(self):
        msgs = [{"role": "user", "content": "remote"}]
        c = _bare_compiler()
        with patch("kegal.compiler.load_text_from_source", return_value=json.dumps(msgs)):
            c.add_chat_history("s", uri="https://example.com/h.json")
        self.assertEqual(c.chat_history["s"], msgs)

    def test_replaces_existing_scope(self):
        c = _bare_compiler()
        c.chat_history["s"] = [{"role": "user", "content": "old"}]
        c.add_chat_history("s", history=[{"role": "user", "content": "new"}])
        self.assertEqual(c.chat_history["s"][0]["content"], "new")

    def test_no_source_raises(self):
        c = _bare_compiler()
        with self.assertRaises(ValueError):
            c.add_chat_history("s")

    def test_two_sources_raises(self):
        c = _bare_compiler()
        with self.assertRaises(ValueError):
            c.add_chat_history("s", history=[], file=Path("x.json"))

    def test_inline_history_is_copied(self):
        """Mutating the original list after add_chat_history must not affect the stored value."""
        c = _bare_compiler()
        msgs = [{"role": "user", "content": "hi"}]
        c.add_chat_history("s", history=msgs)
        msgs.append({"role": "assistant", "content": "extra"})
        self.assertEqual(len(c.chat_history["s"]), 1)


# ---------------------------------------------------------------------------
# add_retrieved_chunks
# ---------------------------------------------------------------------------

class TestAddRetrievedChunks(unittest.TestCase):

    def test_inline_chunks(self):
        c = _bare_compiler()
        c.add_retrieved_chunks(chunks="relevant text")
        self.assertEqual(c.retrieved_chunks, "relevant text")

    def test_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chunks.txt"
            path.write_text("chunk content", encoding="utf-8")
            c = _bare_compiler()
            c.add_retrieved_chunks(file=path)
            self.assertEqual(c.retrieved_chunks, "chunk content")

    def test_from_uri(self):
        c = _bare_compiler()
        with patch("kegal.compiler.load_text_from_source", return_value="remote chunks"):
            c.add_retrieved_chunks(uri="https://example.com/chunks.txt")
        self.assertEqual(c.retrieved_chunks, "remote chunks")

    def test_replaces_existing(self):
        c = _bare_compiler()
        c.retrieved_chunks = "old"
        c.add_retrieved_chunks(chunks="new")
        self.assertEqual(c.retrieved_chunks, "new")

    def test_no_source_raises(self):
        c = _bare_compiler()
        with self.assertRaises(ValueError):
            c.add_retrieved_chunks()

    def test_two_sources_raises(self):
        c = _bare_compiler()
        with self.assertRaises(ValueError):
            c.add_retrieved_chunks(chunks="text", file=Path("x.txt"))


if __name__ == "__main__":
    unittest.main()
