"""End-to-end tests for Cat-2 blackboard sequential chains (`blackboard.chain: true`).

Topology is covered by test_blackboard.py::TestBlackboardChainDagInference.
Here we demonstrate the *new runtime behaviour*: a chained enricher must see in
its own ``{blackboard}`` not only the initial Cat-1 seed but also whatever the
previous chained node wrote — proving the chain actually threads content through,
not just the DAG edges.

Two flavours:
  - TestBlackboardChainMockLLM   — no network, runs everywhere (CI).
  - TestBlackboardChainGraph     — live Ollama, mirrors the tutorial-10 style.
"""

import tempfile
import unittest
from pathlib import Path

from kegal.compiler import Compiler
from kegal.llm.llm_model import LLmResponse

CURRENT_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Mock-LLM end-to-end (CI-safe)
# ---------------------------------------------------------------------------

class _RecordingClient:
    """Stand-in for LlmHandler. Records every complete() call and returns a
    canned response per call in order."""

    model = object()  # Compiler.close() probes client.model for a close() method

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> LLmResponse:
        self.calls.append(kwargs)
        text = self._replies[len(self.calls) - 1]
        return LLmResponse(messages=[text], input_size=1, output_size=1)

    def prompt_text(self, idx: int) -> str:
        """All prompt-bearing strings passed to the idx-th complete() call."""
        kw = self.calls[idx]
        parts = [kw.get("system_prompt"), kw.get("user_message")]
        return "\n".join(p for p in parts if p)


def _chain_source(board_dir: str) -> dict:
    """3-node Cat-2 chain on one board, seeded by a Cat-1 writer."""
    return {
        "models": [{"llm": "ollama", "model": "dummy", "host": "http://localhost:11434"}],
        "user_message": "Topic X",
        "blackboard": {
            "path": board_dir,
            "boards": [{"id": "main", "file": "CHAIN.md", "cleanup": True}],
        },
        "prompts": [
            {  # 0 — seed (Cat-1)
                "template": {
                    "system_template": {"role": "You seed the board."},
                    "prompt_template": {"topic": "{user_message}"},
                }
            },
            {  # 1 — chained enrichers (Cat-2, chain)
                "template": {
                    "system_template": {"role": "You extend the board."},
                    "prompt_template": {"sofar": "{blackboard}"},
                }
            },
        ],
        "nodes": [
            {
                "id": "seed", "model": 0, "temperature": 0.0, "max_tokens": 10,
                "show": False, "blackboard": {"id": "main", "read": False, "write": True},
                "prompt": {"template": 0, "user_message": True},
            },
            {
                "id": "step1", "model": 0, "temperature": 0.0, "max_tokens": 10,
                "show": False,
                "blackboard": {"id": "main", "read": True, "write": True, "chain": True},
                "prompt": {"template": 1},
            },
            {
                "id": "step2", "model": 0, "temperature": 0.0, "max_tokens": 10,
                "show": False,
                "blackboard": {"id": "main", "read": True, "write": True, "chain": True},
                "prompt": {"template": 1},
            },
            {
                "id": "step3", "model": 0, "temperature": 0.0, "max_tokens": 10,
                "show": True,
                "blackboard": {"id": "main", "read": True, "write": True, "chain": True},
                "prompt": {"template": 1},
            },
        ],
        "edges": [
            {"node": "seed"}, {"node": "step1"}, {"node": "step2"}, {"node": "step3"},
        ],
    }


class TestBlackboardChainMockLLM(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.compiler = Compiler(source=_chain_source(self._dir))
        self.client = _RecordingClient(replies=[
            "SEED-alpha", "STEP1-bravo", "STEP2-charlie", "STEP3-delta",
        ])
        self.compiler.clients = [self.client]

    def tearDown(self):
        self.compiler.close()

    def test_chain_threads_written_content_forward(self):
        self.compiler.compile()

        # Nodes ran strictly in chain order: seed, step1, step2, step3
        self.assertEqual(len(self.client.calls), 4)

        p_step1 = self.client.prompt_text(1)
        p_step2 = self.client.prompt_text(2)
        p_step3 = self.client.prompt_text(3)

        # step1 sees only the seed
        self.assertIn("SEED-alpha", p_step1)
        self.assertNotIn("STEP1-bravo", p_step1)

        # step2 sees the seed AND what step1 wrote — the new behaviour
        self.assertIn("SEED-alpha", p_step2)
        self.assertIn("STEP1-bravo", p_step2)
        self.assertNotIn("STEP2-charlie", p_step2)

        # step3 sees the whole accumulated thread
        self.assertIn("SEED-alpha", p_step3)
        self.assertIn("STEP1-bravo", p_step3)
        self.assertIn("STEP2-charlie", p_step3)

        # Final board file holds every contribution in order
        board = (Path(self._dir) / "CHAIN.md").read_text(encoding="utf-8")
        self.assertLess(board.index("SEED-alpha"), board.index("STEP1-bravo"))
        self.assertLess(board.index("STEP1-bravo"), board.index("STEP2-charlie"))
        self.assertLess(board.index("STEP2-charlie"), board.index("STEP3-delta"))

    def test_levels_are_one_node_each(self):
        deps = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)
        self.assertEqual(deps["step2"], {"step1"})
        self.assertEqual(deps["step3"], {"step2"})
        self.assertNotIn("step1", deps["step3"])
        chain_levels = [next(i for i, lv in enumerate(levels) if nid in lv)
                        for nid in ("seed", "step1", "step2", "step3")]
        self.assertEqual(chain_levels, sorted(chain_levels))
        self.assertEqual(len(set(chain_levels)), 4)


# ---------------------------------------------------------------------------
# Live Ollama integration (tutorial-10 style)
# ---------------------------------------------------------------------------

def _ollama_available() -> bool:
    try:
        from ollama import Client
        Client(host="http://localhost:11434").list()
        return True
    except Exception:
        return False


@unittest.skipUnless(_ollama_available(), "Ollama not reachable on localhost:11434")
class TestBlackboardChainGraph(unittest.TestCase):
    graph_path      = CURRENT_DIR / "graphs" / "chain_blackboard_graph.yml"
    blackboard_file = CURRENT_DIR / "graphs" / "CHAIN_BLACKBOARD.md"

    def setUp(self):
        self.compiler = Compiler(uri=str(self.graph_path))

    def tearDown(self):
        self.compiler.close()

    def test_dag_is_a_sequential_chain(self):
        deps   = self.compiler._build_dag()
        levels = self.compiler._topological_levels(deps)
        lvl = lambda nid: next(i for i, lv in enumerate(levels) if nid in lv)
        self.assertLess(lvl("seed"),  lvl("step1"))
        self.assertLess(lvl("step1"), lvl("step2"))
        self.assertLess(lvl("step2"), lvl("step3"))
        self.assertEqual(deps["step3"], {"step2"})
        self.assertNotIn("step1", deps["step3"])

    def test_compile_accumulates_the_thread(self):
        self.compiler.compile()
        executed = {n.node_id for n in self.compiler.get_outputs().nodes}
        self.assertEqual(executed, {"seed", "step1", "step2", "step3"})
        on_disk = self.blackboard_file.read_text(encoding="utf-8")
        # Every node appended something; the board grew past the seed alone.
        self.assertGreater(len(on_disk), 0)
        seed_out = next(
            "\n\n".join(n.response.messages or [])
            for n in self.compiler.get_outputs().nodes if n.node_id == "seed"
        )
        self.assertIn(seed_out.strip()[:40], on_disk)


if __name__ == "__main__":
    unittest.main()
