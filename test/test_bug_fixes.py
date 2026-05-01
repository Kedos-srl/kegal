"""Unit tests for the 9 bug fixes applied in the security/quality review.

All tests are self-contained — no real LLM, no network, no Ollama required.
"""

import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kegal.compiler import Compiler, CompiledOutput
from kegal.compose import compose_node_prompt
from kegal.graph import Graph
from kegal.llm.llm_anthropic import LlmAnthropic
from kegal.llm.llm_model import LLMTool, LLMStructuredSchema, LLmResponse
from kegal.mcp_handler import McpHandler
from kegal.utils import _check_uri_scheme


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _graph_source(**overrides) -> dict:
    base = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [{"template": {"system_template": {}, "prompt_template": {}}}],
        "nodes": [],
        "edges": [],
    }
    base.update(overrides)
    return base


def _node_cfg(nid="n", mp_in=False, mp_out=False, guard=False,
              model=0, template=0, prompt=True) -> dict:
    n: dict = {
        "id": nid,
        "model": model,
        "temperature": 0.0,
        "max_tokens": 10,
        "show": False,
        "message_passing": {"input": mp_in, "output": mp_out},
    }
    if prompt:
        n["prompt"] = {"template": template}
    else:
        n["prompt"] = None
    if guard:
        n["structured_output"] = {
            "type": "object",
            "properties": {"validation": {"type": "boolean"}},
        }
    return n


def _bare_compiler(nodes_cfg=None, edges_cfg=None, extra_prompts=0) -> Compiler:
    """Build a Compiler instance via object.__new__ so no LLM is initialised."""
    nodes_cfg = nodes_cfg or [_node_cfg()]
    edges_cfg = edges_cfg or []

    prompts = [{"template": {"system_template": {}, "prompt_template": {}}}]
    for _ in range(extra_prompts):
        prompts.append({"template": {"system_template": {}, "prompt_template": {}}})

    source = _graph_source(nodes=nodes_cfg, edges=edges_cfg, prompts=prompts)
    graph = Graph.model_validate(source)

    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    c.clients = [MagicMock()]
    c.prompts = [{"system": "", "user": ""}] * len(prompts)
    c.images = None
    c.documents = None
    c.tools = None
    c.chat_history = None
    c.user_message = "hello"
    c.retrieved_chunks = None
    c._board_entries = {}
    c._boards = {}
    c._board_paths = {}
    c._blackboard_lock = threading.Lock()
    c._graph_dir = Path.cwd()
    c._message_passing_lock = threading.Lock()
    c._outputs_lock = threading.Lock()
    c.outputs = CompiledOutput()
    c.message_passing = []
    c.mcp_handlers = {}
    c.tool_executors = {}
    c.graph_mcp_servers = []
    c._react_trace = {}
    c._react_controllers = c._build_react_controller_map()
    return c


# ===========================================================================
# Fix 1: message pipe must NOT be cleared by non-participating nodes
# ===========================================================================

class TestMessagePassingClearFix(unittest.TestCase):

    def _make_response(self, msg="hello"):
        r = LLmResponse()
        r.messages = [msg]
        return r

    def test_non_participating_node_does_not_clear_pipe(self):
        """A node with input=False, output=False must not clear message_passing."""
        c = _bare_compiler([_node_cfg("A", mp_in=False, mp_out=False)])
        c.message_passing = ["upstream data"]

        node = c.nodes["A"]
        response = self._make_response()
        c._check_message_passing(response, node)

        self.assertEqual(c.message_passing, ["upstream data"],
                         "Non-participating node must not wipe message_passing")

    def test_output_node_appends_to_pipe(self):
        """A node with output=True must append its response to message_passing."""
        c = _bare_compiler([_node_cfg("A", mp_out=True)])
        node = c.nodes["A"]
        response = self._make_response("result")
        c._check_message_passing(response, node)

        self.assertIn("result", c.message_passing)

    def test_non_participating_preserves_existing_data_across_parallel(self):
        """Parallel non-participating nodes must never race-clear the pipe."""
        c = _bare_compiler([_node_cfg("A"), _node_cfg("B")])
        c.message_passing = ["important"]

        def call(nid):
            c._check_message_passing(LLmResponse(), c.nodes[nid])

        threads = [threading.Thread(target=call, args=(n,)) for n in ["A", "B"]]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(c.message_passing, ["important"])


# ===========================================================================
# Fix 2: Anthropic tool schema — input_schema must be a proper JSON Schema
# ===========================================================================

class TestAnthropicToolSchema(unittest.TestCase):

    def _make_tool(self, name="search", description="Search KB"):
        return LLMTool(
            name=name,
            description=description,
            parameters={"query": LLMStructuredSchema(type="string", description="Search query")},
            required=["query"],
        )

    def test_input_schema_is_json_schema_object(self):
        """input_schema must contain type/properties/required, not the raw tool dict."""
        tools = [self._make_tool()]
        result = LlmAnthropic._tools_data(tools)

        self.assertEqual(len(result), 1)
        schema = result[0]
        self.assertIn("input_schema", schema)
        inp = schema["input_schema"]

        self.assertEqual(inp["type"], "object")
        self.assertIn("properties", inp)
        self.assertIn("required", inp)

    def test_input_schema_does_not_contain_name_or_description(self):
        """Top-level tool name/description must not leak into input_schema."""
        tools = [self._make_tool()]
        result = LlmAnthropic._tools_data(tools)
        inp = result[0]["input_schema"]

        self.assertNotIn("name", inp)
        self.assertNotIn("description", inp)

    def test_tool_name_and_description_at_top_level(self):
        """name and description must still appear at the top level of each tool dict."""
        tools = [self._make_tool(name="my_tool", description="does stuff")]
        result = LlmAnthropic._tools_data(tools)
        self.assertEqual(result[0]["name"], "my_tool")
        self.assertEqual(result[0]["description"], "does stuff")

    def test_multiple_tools_all_correct(self):
        tools = [self._make_tool("t1"), self._make_tool("t2")]
        result = LlmAnthropic._tools_data(tools)
        for item in result:
            self.assertIn("type", item["input_schema"])
            self.assertIn("properties", item["input_schema"])


# ===========================================================================
# Fix 3: guard node with prompt=None must raise, not silently pass
# ===========================================================================

class TestGuardNodeNullPrompt(unittest.TestCase):

    def test_guard_node_without_prompt_raises(self):
        """A guard node (structured_output with validation) that has no prompt
        must be caught at init time by _validate_indices, not silently pass."""
        c = _bare_compiler([_node_cfg("guard", guard=True, prompt=False)])
        node = c.nodes["guard"]
        node.prompt = None  # force null prompt

        with self.assertRaises(ValueError, msg="Guard with no prompt must raise"):
            c._validate_indices()

    def test_regular_node_without_prompt_returns_true(self):
        """A non-guard node with no prompt silently succeeds (no LLM call needed)."""
        c = _bare_compiler([_node_cfg("plain", prompt=False)])
        node = c.nodes["plain"]
        node.prompt = None

        result = c._run_node(node)
        self.assertTrue(result)


# ===========================================================================
# Fix 4: compile() must reset outputs and message_passing on each call
# ===========================================================================

class TestCompileResetsState(unittest.TestCase):

    def _compiler_with_mock_run(self):
        """Return a compiler whose _run_node is mocked to succeed instantly."""
        c = _bare_compiler([_node_cfg("A")])
        fake_response = LLmResponse()
        fake_response.messages = ["ok"]

        def fake_run(node):
            from kegal.compiler import CompiledNodeOutput
            with c._outputs_lock:
                c.outputs.nodes.append(CompiledNodeOutput(
                    node_id=node.id,
                    response=fake_response,
                    compiled_time=0.0,
                    show=False,
                    history=False,
                ))
            return True

        c._run_node = fake_run
        return c

    def test_second_compile_does_not_accumulate_nodes(self):
        """After a second compile() call, outputs.nodes must reflect only that run."""
        c = self._compiler_with_mock_run()

        c.compile()
        first_count = len(c.outputs.nodes)
        self.assertEqual(first_count, 1)

        c.compile()
        second_count = len(c.outputs.nodes)
        self.assertEqual(second_count, 1,
                         "Outputs must be reset between compile() calls, not accumulated")

    def test_message_passing_reset_on_compile(self):
        """message_passing must be empty at the start of each compile() run."""
        c = _bare_compiler([_node_cfg("A")])
        c.message_passing = ["stale data from previous run"]

        with patch.object(c, "_run_node", return_value=True):
            c.compile()

        # After compile starts, message_passing should have been cleared (it's [] before any node writes)
        # We test by confirming stale data is gone (nodes write nothing since mock returns True)
        self.assertEqual(c.message_passing, [])


# ===========================================================================
# Fix 5: compose_node_prompt must not mutate the caller's placeholders dict
# ===========================================================================

class TestComposeProcedureMutation(unittest.TestCase):

    def test_original_placeholders_not_mutated(self):
        """compose_node_prompt must not add user_message/message_passing/retrieved_chunks
        to the dict passed by the caller."""
        original = {"domain": "energy"}
        original_copy = dict(original)

        template = {"system": "You are an expert in {domain}.",
                    "user": "Respond to: {user_message}"}

        compose_node_prompt(
            prompt_template=template,
            placeholders=original,
            user_message="tell me about solar",
        )

        self.assertEqual(original, original_copy,
                         "compose_node_prompt must not modify the caller's placeholders dict")

    def test_result_contains_substituted_values(self):
        """Even though original is not mutated, the returned template must be filled."""
        template = {"system": "", "user": "Focus on {domain}. Message: {user_message}"}
        result = compose_node_prompt(
            prompt_template=template,
            placeholders={"domain": "wind power"},
            user_message="How efficient is it?",
        )
        self.assertIn("wind power", result["user"])
        self.assertIn("How efficient is it?", result["user"])

    def test_empty_placeholders_not_mutated(self):
        """Works correctly even when starting from an empty placeholders dict."""
        original = {}
        template = {"system": "", "user": "Hello {user_message}"}
        compose_node_prompt(
            prompt_template=template,
            placeholders=original,
            user_message="hi",
        )
        self.assertEqual(original, {})


# ===========================================================================
# Fix 6: McpHandler must pass call_timeout to future.result()
# ===========================================================================

class TestMcpHandlerTimeout(unittest.TestCase):

    def _make_server_cfg(self, transport="stdio"):
        from kegal.graph import GraphMcpServer
        if transport == "stdio":
            return GraphMcpServer(id="s", transport="stdio", command="echo", args=[])
        return GraphMcpServer(id="s", transport="sse", url="http://localhost/sse")

    def test_default_call_timeout_is_set(self):
        """McpHandler must have a non-None call_timeout attribute."""
        from kegal.mcp_handler import _DEFAULT_CALL_TIMEOUT
        h = object.__new__(McpHandler)
        h._call_timeout = _DEFAULT_CALL_TIMEOUT
        self.assertIsNotNone(h._call_timeout)
        self.assertGreater(h._call_timeout, 0)

    def test_custom_timeout_stored(self):
        """McpHandler stores a caller-supplied call_timeout."""
        cfg = self._make_server_cfg()
        # Prevent actual thread/loop startup by patching threading.Thread
        with patch("kegal.mcp_handler.threading.Thread") as mock_thread, \
             patch("kegal.mcp_handler.asyncio.new_event_loop") as mock_loop:
            mock_thread.return_value = MagicMock()
            mock_loop.return_value = MagicMock()
            h = McpHandler(cfg, call_timeout=120)
        self.assertEqual(h._call_timeout, 120)

    def test_run_passes_timeout_to_future_result(self):
        """_run() must call future.result(timeout=self._call_timeout)."""
        cfg = self._make_server_cfg()
        with patch("kegal.mcp_handler.threading.Thread") as mock_thread, \
             patch("kegal.mcp_handler.asyncio.new_event_loop") as mock_loop:
            mock_thread.return_value = MagicMock()
            mock_loop.return_value = MagicMock()
            h = McpHandler(cfg, call_timeout=42)

        mock_future = MagicMock()
        mock_future.result.return_value = "ok"

        with patch("kegal.mcp_handler.asyncio.run_coroutine_threadsafe",
                   return_value=mock_future):
            h._run(MagicMock())  # coro is ignored since we mock run_coroutine_threadsafe

        mock_future.result.assert_called_once_with(timeout=42)


# ===========================================================================
# Fix 7: tool loop must NOT exit early for message_passing.output nodes
# ===========================================================================

class TestToolLoopNoEarlyExit(unittest.TestCase):

    def _compiler_with_tool_node(self, mp_out: bool):
        c = _bare_compiler([_node_cfg("T", mp_out=mp_out)])
        c.nodes["T"].tools = ["my_tool"]
        c.tools = [LLMTool(
            name="my_tool",
            description="test tool",
            parameters={"q": LLMStructuredSchema(type="string")},
            required=["q"],
        )]
        return c

    def _response_with_tool_call(self):
        from kegal.llm.llm_model import LLMFunctionCall
        r = LLmResponse()
        r.tools = [LLMFunctionCall(name="my_tool", parameters={"q": "x"})]
        return r

    def _final_response(self):
        r = LLmResponse()
        r.messages = ["final answer"]
        r.tools = None
        return r

    def test_tool_loop_continues_to_get_llm_synthesis(self):
        """After executing tool calls, the loop must call the LLM again for a
        final answer — regardless of message_passing.output value."""
        for mp_out in (True, False):
            with self.subTest(mp_out=mp_out):
                c = self._compiler_with_tool_node(mp_out)

                call_count = {"n": 0}
                tool_response = self._response_with_tool_call()
                final = self._final_response()

                def fake_complete(**kwargs):
                    call_count["n"] += 1
                    return tool_response if call_count["n"] == 1 else final

                client_mock = MagicMock()
                client_mock.complete.side_effect = fake_complete
                c.clients = [client_mock]

                with patch.object(c, "_execute_tool_call", return_value="tool result"):
                    body = {
                        "temperature": 0.0,
                        "max_tokens": 10,
                        "user_message": "test",
                    }
                    result = c._run_tool_loop(c.nodes["T"], body)

                self.assertGreaterEqual(call_count["n"], 2,
                    f"LLM must be called at least twice (tool + synthesis) when mp_out={mp_out}")
                self.assertIsNotNone(result.messages,
                    "Final response must contain synthesized messages")


# ===========================================================================
# Fix 8: out-of-range model/template indices must raise ValueError at init
# ===========================================================================

class TestIndexBoundsValidation(unittest.TestCase):

    def _source_with_node(self, model_idx=0, template_idx=0, n_models=1, n_prompts=1):
        prompts = [{"template": {}} for _ in range(n_prompts)]
        models = [{"llm": "ollama", "model": "dummy"} for _ in range(n_models)]
        return {
            "models": models,
            "prompts": prompts,
            "nodes": [_node_cfg("A", model=model_idx, template=template_idx)],
            "edges": [],
        }

    def test_valid_indices_do_not_raise(self):
        """model=0, template=0 with one model and one prompt must not raise."""
        c = _bare_compiler([_node_cfg("A", model=0, template=0)])
        c._validate_indices()  # should not raise

    def test_out_of_range_model_raises(self):
        """model index beyond the models list must raise ValueError."""
        c = _bare_compiler([_node_cfg("A", model=5)])  # only 1 client (index 0)
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("model", str(ctx.exception).lower())
        self.assertIn("A", str(ctx.exception))

    def test_out_of_range_template_raises(self):
        """template index beyond the prompts list must raise ValueError."""
        c = _bare_compiler([_node_cfg("A", template=99)])  # only 1 prompt (index 0)
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        self.assertIn("template", str(ctx.exception).lower())
        self.assertIn("A", str(ctx.exception))

    def test_multiple_errors_reported_together(self):
        """All out-of-range nodes are reported in a single ValueError."""
        c = _bare_compiler([
            _node_cfg("A", model=9),
            _node_cfg("B", template=9),
        ])
        with self.assertRaises(ValueError) as ctx:
            c._validate_indices()
        msg = str(ctx.exception)
        self.assertIn("A", msg)
        self.assertIn("B", msg)

    def test_node_without_prompt_skips_template_check(self):
        """Nodes with no prompt must not be checked for template index."""
        c = _bare_compiler([_node_cfg("A", prompt=False)])
        node = c.nodes["A"]
        node.prompt = None
        c._validate_indices()  # must not raise


# ===========================================================================
# Fix 9: SSRF — only HTTPS URIs are permitted
# ===========================================================================

class TestUriSchemeGuard(unittest.TestCase):

    def test_https_allowed(self):
        """HTTPS URIs must pass the check without raising."""
        _check_uri_scheme("https://example.com/data.yml")

    def test_http_rejected(self):
        """Plain HTTP must be rejected (SSRF risk via cleartext + internal targets)."""
        with self.assertRaises(ValueError) as ctx:
            _check_uri_scheme("http://169.254.169.254/latest/meta-data/")
        self.assertIn("http", str(ctx.exception))

    def test_file_scheme_rejected(self):
        """file:// URIs must be rejected."""
        with self.assertRaises(ValueError):
            _check_uri_scheme("file:///etc/passwd")

    def test_ftp_rejected(self):
        """ftp:// must be rejected."""
        with self.assertRaises(ValueError):
            _check_uri_scheme("ftp://internal-host/data")

    def test_local_path_no_scheme_passes(self):
        """Paths without a scheme (local files) must pass — they are not URLs."""
        _check_uri_scheme("/home/user/graph.yml")
        _check_uri_scheme("relative/path.yml")

    def test_load_text_rejects_http(self):
        """load_text_from_source must reject http:// before making any network call."""
        from kegal.utils import load_text_from_source
        with self.assertRaises(ValueError):
            load_text_from_source("http://internal-service/secret")

    def test_load_binary_rejects_http(self):
        """_load_binary_from_source must reject http:// before fetching."""
        from kegal.utils import load_images_to_base64
        # Will hit _check_uri_scheme before any network call
        with self.assertRaises(ValueError):
            load_images_to_base64("http://attacker.com/evil.png")


if __name__ == "__main__":
    unittest.main()
