"""
Unit and integration tests for the CLI tools_module loading feature.

Tests target:
  - _load_tool_executors()  (TestLoadToolExecutors)
  - _KNOWN_CONFIG_KEYS       (tools_module must not trigger unknown-key warning)
  - _cmd_run integration     (TestCmdRunWithToolsModule)
"""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kegal.cli import _load_tool_executors, _KNOWN_CONFIG_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(directory: Path, filename: str, content: str) -> Path:
    """Write dedented content to a file inside directory and return its Path."""
    p = directory / filename
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ===========================================================================
# TestLoadToolExecutors
# ===========================================================================

class TestLoadToolExecutors(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        # Remove any cached module so tests don't interfere with each other
        sys.modules.pop("kegal_tools", None)
        self._tmp.cleanup()

    def test_valid_module_returns_executors(self):
        """A tools.py with a non-empty tool_executors dict returns the dict."""
        _write(self.project, "tools.py", """
            def greet(name: str) -> str:
                return f"Hello {name}"

            tool_executors = {"greet": greet}
        """)
        result = _load_tool_executors(self.project, "tools.py")
        self.assertIn("greet", result)
        self.assertEqual(result["greet"]("World"), "Hello World")

    def test_missing_file_raises_value_error(self):
        """A path that does not exist on disk raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _load_tool_executors(self.project, "nonexistent.py")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_missing_tool_executors_attribute_raises(self):
        """A module that defines no tool_executors raises ValueError."""
        _write(self.project, "tools.py", "x = 42\n")
        with self.assertRaises(ValueError) as ctx:
            _load_tool_executors(self.project, "tools.py")
        self.assertIn("tool_executors", str(ctx.exception))

    def test_empty_dict_raises_value_error(self):
        """tool_executors = {} (empty) raises ValueError."""
        _write(self.project, "tools.py", "tool_executors = {}\n")
        with self.assertRaises(ValueError):
            _load_tool_executors(self.project, "tools.py")

    def test_non_dict_raises_value_error(self):
        """tool_executors set to a non-dict value raises ValueError."""
        _write(self.project, "tools.py", 'tool_executors = "not a dict"\n')
        with self.assertRaises(ValueError):
            _load_tool_executors(self.project, "tools.py")

    def test_multiple_executors_all_returned(self):
        """All functions in a multi-entry tool_executors dict are returned."""
        _write(self.project, "tools.py", """
            def add(a: int, b: int) -> int:
                return a + b

            def upper(text: str) -> str:
                return text.upper()

            tool_executors = {"add": add, "upper": upper}
        """)
        result = _load_tool_executors(self.project, "tools.py")
        self.assertEqual(set(result.keys()), {"add", "upper"})
        self.assertEqual(result["add"](2, 3), 5)
        self.assertEqual(result["upper"]("hello"), "HELLO")

    def test_path_resolved_relative_to_project(self):
        """The rel_path is resolved relative to project_path, not cwd."""
        _write(self.project, "my_tools.py", """
            tool_executors = {"noop": lambda: None}
        """)
        # Should work even if cwd is different
        result = _load_tool_executors(self.project, "my_tools.py")
        self.assertIn("noop", result)


# ===========================================================================
# TestKnownConfigKeys
# ===========================================================================

class TestKnownConfigKeys(unittest.TestCase):

    def test_tools_module_is_known_key(self):
        """tools_module must be in _KNOWN_CONFIG_KEYS to avoid spurious warnings."""
        self.assertIn("tools_module", _KNOWN_CONFIG_KEYS)


# ===========================================================================
# TestCmdRunWithToolsModule
# ===========================================================================

class TestCmdRunWithToolsModule(unittest.TestCase):
    """Integration tests that verify _cmd_run passes tool_executors to Compiler."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        sys.modules.pop("kegal_tools", None)
        self._tmp.cleanup()

    def _write_project(self, tools_module_line: str = "") -> None:
        """Write a minimal kegal.yml, graph.yml, and tools.py."""
        _write(self.project, "kegal.yml", f"""
            graph: graph.yml
            mode: once
            {tools_module_line}
        """)
        _write(self.project, "graph.yml", """
            models:
              - llm: "ollama"
                model: "dummy"
            prompts:
              - template:
                  system_template:
                    role: "assistant"
                  prompt_template:
                    q: "{user_message}"
            nodes:
              - id: "n"
                model: 0
                temperature: 0.0
                max_tokens: 64
                show: true
                prompt:
                  template: 0
                  user_message: true
            edges:
              - node: "n"
        """)
        _write(self.project, "tools.py", """
            def ping() -> str:
                return "pong"

            tool_executors = {"ping": ping}
        """)

    def _make_args(self) -> MagicMock:
        args = MagicMock()
        args.path = str(self.project)
        return args

    def test_tools_module_executors_passed_to_compiler(self):
        """When tools_module is set, Compiler receives the loaded tool_executors."""
        self._write_project("tools_module: ./tools.py")
        captured = {}

        def fake_compiler(uri, tool_executors=None):
            captured["tool_executors"] = tool_executors
            cm = MagicMock()
            cm.__enter__ = lambda s: cm
            cm.__exit__ = MagicMock(return_value=False)
            cm.get_outputs.return_value = MagicMock(nodes=[])
            return cm

        with patch("kegal.cli.Compiler", side_effect=fake_compiler):
            from kegal.cli import _cmd_run
            _cmd_run(self._make_args())

        self.assertIsNotNone(captured.get("tool_executors"))
        self.assertIn("ping", captured["tool_executors"])

    def test_no_tools_module_compiler_gets_none(self):
        """When tools_module is absent, Compiler is called without tool_executors."""
        self._write_project()   # no tools_module line
        captured = {}

        def fake_compiler(uri, tool_executors=None):
            captured["tool_executors"] = tool_executors
            cm = MagicMock()
            cm.__enter__ = lambda s: cm
            cm.__exit__ = MagicMock(return_value=False)
            cm.get_outputs.return_value = MagicMock(nodes=[])
            return cm

        with patch("kegal.cli.Compiler", side_effect=fake_compiler):
            from kegal.cli import _cmd_run
            _cmd_run(self._make_args())

        self.assertIsNone(captured.get("tool_executors"))

    def test_missing_tools_module_file_exits_with_error(self):
        """A tools_module path that doesn't exist makes the CLI exit with code 1."""
        self._write_project("tools_module: ./missing.py")

        with patch("kegal.cli.Compiler"):
            from kegal.cli import _cmd_run
            with self.assertRaises(SystemExit) as ctx:
                _cmd_run(self._make_args())
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
