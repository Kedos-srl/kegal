"""
Research-synthesis ReAct test — complex multi-step scenario.

Scenario: a research_controller orchestrates three specialist agents in sequence:
  1. history_agent  — retrieves a historical fact
  2. science_agent  — retrieves a scientific fact
  3. writer_agent   — synthesises both facts into a paragraph

Unit tests (mocked LLM) verify:
  - full 3-step dispatch sequence with correct ordering
  - observation messages from previous agents are visible in the controller
    conversation before subsequent dispatches
  - same agent can be dispatched more than once with different inputs
  - early termination at max_iterations leaves done=False in the trace
  - ReactTrace accurately records every iteration's outputs and token counts

Integration tests (Ollama) verify:
  - graph topology (DAG exclusion, controller detection)
  - compile() produces a controller output entry
  - react trace is saved as a standalone markdown file (controller view only)
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kegal.compiler import Compiler, ReactTrace
from kegal.graph import Graph

CURRENT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Shared compiler factory
# ---------------------------------------------------------------------------

def _build_research_compiler():
    """Return (compiler_instance, mock_client) for the 3-agent research graph."""
    source = {
        "models": [{"llm": "ollama", "model": "dummy"}],
        "prompts": [
            # 0 — controller
            {"template": {"system_template": {"role": "coordinator"},
                           "prompt_template": {"task": "{user_message}"}}},
            # 1 — history agent
            {"template": {"system_template": {},
                           "prompt_template": {"q": "{message_passing}"}}},
            # 2 — science agent
            {"template": {"system_template": {},
                           "prompt_template": {"q": "{message_passing}"}}},
            # 3 — writer agent
            {"template": {"system_template": {},
                           "prompt_template": {"f": "{message_passing}"}}},
        ],
        "user_message": "Write a brief electricity report.",
        "nodes": [
            {
                "id": "research_controller", "model": 0,
                "temperature": 0.0, "max_tokens": 600,
                "show": True,
                "prompt": {"template": 0, "user_message": True},
                "react": {"max_iterations": 8},
                "react_output": {
                    "type": "object",
                    "properties": {
                        "next_agent":   {"type": "string"},
                        "agent_input":  {"type": "string"},
                        "done":         {"type": "boolean"},
                        "final_answer": {"type": "string"},
                        "reasoning":    {"type": "string"},
                    },
                    "required": ["done"],
                },
            },
            {"id": "history_agent", "model": 0, "temperature": 0.0, "max_tokens": 80,
             "show": True, "message_passing": {"input": True, "output": True},
             "prompt": {"template": 1}},
            {"id": "science_agent", "model": 0, "temperature": 0.0, "max_tokens": 80,
             "show": True, "message_passing": {"input": True, "output": True},
             "prompt": {"template": 2}},
            {"id": "writer_agent", "model": 0, "temperature": 0.0, "max_tokens": 150,
             "show": True, "message_passing": {"input": True, "output": True},
             "prompt": {"template": 3}},
        ],
        "edges": [{"node": "research_controller", "react": [
            {"node": "history_agent"},
            {"node": "science_agent"},
            {"node": "writer_agent"},
        ]}],
    }
    graph = Graph.model_validate(source)
    mock_client = MagicMock()

    c = object.__new__(Compiler)
    c.nodes = {n.id: n for n in graph.nodes}
    c.edges = graph.edges
    c.prompts = Compiler._load_prompt_inputs(graph.prompts)
    c.react_compact_prompts = []
    c.user_message = graph.user_message
    c.retrieved_chunks = None
    c.chat_history = None
    c.images = None
    c.documents = None
    c.tools = None
    c.blackboard = ""
    c._blackboard_path = None
    c.mcp_handlers = {}
    c.tool_executors = {}
    c.message_passing = []
    c.graph_mcp_servers = []
    c._react_trace = {}
    c._react_controllers = c._build_react_controller_map()
    c._outputs_lock = __import__("threading").Lock()
    c._message_passing_lock = __import__("threading").Lock()
    c._blackboard_lock = __import__("threading").Lock()
    from kegal.compiler import CompiledOutput
    c.outputs = CompiledOutput()
    c.clients = [mock_client]
    c.context_windows = [m.context_window for m in graph.models]
    return c, mock_client


def _resp(routing: dict, input_size: int = 50, output_size: int = 20):
    from kegal.llm.llm_model import LLmResponse
    return LLmResponse(
        json_output=routing,
        messages=[str(routing)],
        input_size=input_size,
        output_size=output_size,
    )


# ---------------------------------------------------------------------------
# Unit tests — mocked LLM, all steps deterministic
# ---------------------------------------------------------------------------

class TestReactResearch(unittest.TestCase):

    def test_three_step_sequence(self):
        """Controller dispatches history → science → writer then signals done.
        Trace must record all three iterations in order."""
        c, mock_client = _build_research_compiler()
        mock_client.complete.side_effect = [
            _resp({"next_agent": "history_agent",
                   "agent_input": "Who invented the light bulb?",
                   "done": False, "reasoning": "Step 1: gather inventor fact"}),
            _resp({"next_agent": "science_agent",
                   "agent_input": "What is Ohm's law?",
                   "done": False, "reasoning": "Step 2: gather science fact"}),
            _resp({"next_agent": "writer_agent",
                   "agent_input": "Fact 1: Thomas Edison invented the light bulb in 1879. "
                                  "Fact 2: Ohm's law states V = I × R.",
                   "done": False, "reasoning": "Step 3: synthesise into paragraph"}),
            _resp({"done": True,
                   "final_answer": "Edison invented the light bulb (1879); "
                                   "Ohm's law (V=IR) governs electrical circuits."}),
        ]
        ctrl_edge = c._react_controllers["research_controller"]
        with patch.object(c, "_run_react_agent", side_effect=[
            "Thomas Edison invented the light bulb in 1879.",
            "Ohm's law: voltage equals current times resistance (V = I × R).",
            "Electricity was transformed by Edison's light bulb and governed by Ohm's law.",
        ]):
            c._run_react_loop(ctrl_edge, c.nodes["research_controller"])

        trace = c.get_react_trace("research_controller")
        self.assertEqual(trace.total_iterations, 3)
        self.assertEqual(
            [it.agent_name for it in trace.iterations],
            ["history_agent", "science_agent", "writer_agent"],
        )
        self.assertTrue(trace.done)
        self.assertIn("Edison", trace.final_answer)

    def test_observations_visible_before_writer(self):
        """When the controller calls writer_agent (3rd dispatch) its conversation
        buffer must already contain the observation replies from history_agent
        and science_agent."""
        c, mock_client = _build_research_compiler()
        captured: list[list] = []

        def recording_complete(**kwargs):
            captured.append(list(kwargs.get("chat_history") or []))
            idx = len(captured)
            if idx == 1:
                return _resp({"next_agent": "history_agent",
                               "agent_input": "light bulb?", "done": False})
            if idx == 2:
                return _resp({"next_agent": "science_agent",
                               "agent_input": "Ohm's law?", "done": False})
            if idx == 3:
                return _resp({"next_agent": "writer_agent",
                               "agent_input": "both facts", "done": False})
            return _resp({"done": True, "final_answer": "Report complete."})

        mock_client.complete.side_effect = recording_complete
        ctrl_edge = c._react_controllers["research_controller"]
        with patch.object(c, "_run_react_agent", side_effect=[
            "Edison fact.", "Ohm fact.", "Written paragraph.",
        ]):
            c._run_react_loop(ctrl_edge, c.nodes["research_controller"])

        # captured[2] is the conversation the controller sees on the 3rd call (→ writer)
        conv_texts = [m.content for m in captured[2]]
        self.assertTrue(
            any("history_agent" in t for t in conv_texts),
            "history_agent observation must appear in conversation before writer is called",
        )
        self.assertTrue(
            any("science_agent" in t for t in conv_texts),
            "science_agent observation must appear in conversation before writer is called",
        )

    def test_trace_records_outputs_and_tokens(self):
        """ReactTrace stores each iteration's agent_output and accumulates tokens."""
        c, mock_client = _build_research_compiler()
        mock_client.complete.side_effect = [
            _resp({"next_agent": "history_agent", "agent_input": "q1", "done": False},
                  input_size=40, output_size=10),
            _resp({"next_agent": "science_agent",  "agent_input": "q2", "done": False},
                  input_size=60, output_size=12),
            _resp({"next_agent": "writer_agent",   "agent_input": "q3", "done": False},
                  input_size=80, output_size=15),
            _resp({"done": True, "final_answer": "Report."},
                  input_size=100, output_size=20),
        ]
        ctrl_edge = c._react_controllers["research_controller"]
        with patch.object(c, "_run_react_agent", side_effect=["h_out", "s_out", "w_out"]):
            c._run_react_loop(ctrl_edge, c.nodes["research_controller"])

        trace = c.get_react_trace("research_controller")
        self.assertEqual(len(trace.iterations), 3)
        self.assertEqual(trace.iterations[0].agent_output, "h_out")
        self.assertEqual(trace.iterations[1].agent_output, "s_out")
        self.assertEqual(trace.iterations[2].agent_output, "w_out")
        self.assertEqual(trace.total_controller_input_tokens,  40 + 60 + 80 + 100)
        self.assertEqual(trace.total_controller_output_tokens, 10 + 12 + 15 + 20)

    def test_early_stop_at_max_iterations(self):
        """Loop stops after max_iterations; done is False; writer is never called."""
        c, mock_client = _build_research_compiler()
        c.nodes["research_controller"].react.max_iterations = 2
        mock_client.complete.side_effect = [
            _resp({"next_agent": "history_agent", "agent_input": "q1", "done": False}),
            _resp({"next_agent": "science_agent",  "agent_input": "q2", "done": False}),
            # writer iteration never reached
        ]
        ctrl_edge = c._react_controllers["research_controller"]
        with patch.object(c, "_run_react_agent", return_value="output"):
            c._run_react_loop(ctrl_edge, c.nodes["research_controller"])

        trace = c.get_react_trace("research_controller")
        self.assertEqual(trace.total_iterations, 2)
        self.assertFalse(trace.done)
        agent_names = [it.agent_name for it in trace.iterations]
        self.assertNotIn("writer_agent", agent_names)

    def test_same_agent_dispatched_twice(self):
        """The controller may call the same agent multiple times with different inputs."""
        c, mock_client = _build_research_compiler()
        mock_client.complete.side_effect = [
            _resp({"next_agent": "history_agent",
                   "agent_input": "Who invented the light bulb?", "done": False}),
            _resp({"next_agent": "history_agent",
                   "agent_input": "Who invented the telephone?",  "done": False}),
            _resp({"done": True, "final_answer": "Two inventors gathered."}),
        ]
        ctrl_edge = c._react_controllers["research_controller"]
        with patch.object(c, "_run_react_agent",
                          side_effect=["Edison answer.", "Bell answer."]):
            c._run_react_loop(ctrl_edge, c.nodes["research_controller"])

        trace = c.get_react_trace("research_controller")
        self.assertEqual(trace.total_iterations, 2)
        self.assertEqual(trace.iterations[0].agent_name, "history_agent")
        self.assertEqual(trace.iterations[1].agent_name, "history_agent")
        self.assertEqual(trace.iterations[0].agent_input, "Who invented the light bulb?")
        self.assertEqual(trace.iterations[1].agent_input, "Who invented the telephone?")
        self.assertTrue(trace.done)

    def test_three_agents_registered_in_controller(self):
        """All three specialist agents must be present in the react edge list."""
        c, _ = _build_research_compiler()
        ctrl_edge = c._react_controllers["research_controller"]
        agent_names = {e.node for e in ctrl_edge.react}
        self.assertEqual(agent_names, {"history_agent", "science_agent", "writer_agent"})

    def test_agent_nodes_excluded_from_dag(self):
        """Specialist agent nodes must not appear in the main DAG."""
        c, _ = _build_research_compiler()
        deps = c._build_dag()
        self.assertIn("research_controller", deps)
        for agent in ("history_agent", "science_agent", "writer_agent"):
            self.assertNotIn(agent, deps,
                             f"'{agent}' must be excluded from the main DAG")


# ---------------------------------------------------------------------------
# Integration tests — requires Ollama running locally
# ---------------------------------------------------------------------------

class TestReactResearchIntegration(unittest.TestCase):
    """Integration tests against a real Ollama instance.

    compile() is called once in setUpClass so all tests share a single
    LLM run — one coherent log stream, no repeated Ollama round-trips.
    """
    graph_path = CURRENT_DIR / "graphs" / "react_research_graph.yml"

    @classmethod
    def setUpClass(cls):
        cls.compiler = Compiler(uri=str(cls.graph_path))
        cls.compiler.compile()
        cls.trace = cls.compiler.get_react_trace("research_controller")

    @classmethod
    def tearDownClass(cls):
        cls.compiler.close()

    def test_dag_excludes_all_agent_nodes(self):
        deps = self.compiler._build_dag()
        self.assertIn("research_controller", deps)
        for agent in ("history_agent", "science_agent", "writer_agent"):
            self.assertNotIn(agent, deps)

    def test_controller_and_agents_detected(self):
        self.assertIn("research_controller", self.compiler._react_controllers)
        ctrl_edge = self.compiler._react_controllers["research_controller"]
        agent_names = {e.node for e in ctrl_edge.react}
        self.assertIn("history_agent", agent_names)
        self.assertIn("science_agent", agent_names)
        self.assertIn("writer_agent", agent_names)

    def test_compile_produces_controller_output(self):
        executed = {n.node_id for n in self.compiler.get_outputs().nodes}
        self.assertIn("research_controller", executed)

    def test_trace_is_populated(self):
        self.assertIsNotNone(self.trace)
        self.assertIsInstance(self.trace, ReactTrace)

    def test_trace_has_iterations(self):
        """Skip if the small model did not dispatch any agent."""
        if self.trace.total_iterations == 0:
            self.skipTest(
                "Model dispatched no agents — small models sometimes skip agent calls. "
                "Run with a larger model for a complete integration check."
            )
        self.assertGreater(self.trace.total_iterations, 0)

    def test_save_outputs_and_trace(self):
        """Save compiled outputs and ReAct controller trace to disk.

        Three files are written to graph_outputs/react_research_graph/:
          - react_research_graph.json        — compiled output for all main-graph nodes
          - react_research_graph.md          — same in markdown (one section per node)
          - react_research_graph_trace.md    — ReAct controller trace: one section per
            iteration with the controller's reasoning, agent input, and agent response.

        Agent nodes run in isolation so their responses only appear inside the
        trace iterations, not as separate node sections in the markdown output.
        """
        out_dir = CURRENT_DIR / "graph_outputs" / "react_research_graph"
        out_dir.mkdir(parents=True, exist_ok=True)

        self.compiler.save_outputs_as_json(out_dir / "react_research_graph.json")
        self.compiler.save_outputs_as_markdown(out_dir / "react_research_graph.md")

        trace = self.trace
        md = "# ReAct Controller Trace — research_controller\n\n"
        md += "| Field | Value |\n|---|---|\n"
        md += f"| Done | {trace.done} |\n"
        md += f"| Total iterations | {trace.total_iterations} |\n"
        md += f"| Controller input tokens | {trace.total_controller_input_tokens} |\n"
        md += f"| Controller output tokens | {trace.total_controller_output_tokens} |\n\n"
        if trace.final_answer:
            md += f"**Final answer:**\n\n{trace.final_answer}\n\n"
        md += "---\n\n"
        for it in trace.iterations:
            md += f"## Iteration {it.iteration} — `{it.agent_name}`\n\n"
            if it.reasoning:
                md += f"**Controller reasoning:** {it.reasoning}\n\n"
            md += f"**Input sent to agent:**\n\n> {it.agent_input}\n\n"
            md += f"**Agent response observed by controller:**\n\n{it.agent_output}\n\n"
            md += (f"*Controller tokens this step — "
                   f"in: {it.controller_input_tokens}, "
                   f"out: {it.controller_output_tokens}*\n\n")
            md += "---\n\n"

        trace_path = out_dir / "react_research_graph_trace.md"
        trace_path.write_text(md, encoding="utf-8")

        self.assertTrue((out_dir / "react_research_graph.json").exists())
        self.assertTrue((out_dir / "react_research_graph.md").exists())
        self.assertTrue(trace_path.exists())


if __name__ == "__main__":
    unittest.main()
