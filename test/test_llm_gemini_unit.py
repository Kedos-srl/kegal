"""Unit tests for LlmGemini — no Google API key required (google.genai is mocked)."""
import sys
import json
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_genai_mocks():
    """Return (mock_google, mock_genai, mock_types) ready to patch sys.modules."""
    mock_types = MagicMock()
    mock_genai = MagicMock()
    mock_google = MagicMock()
    mock_google.genai = mock_genai
    mock_genai.types = mock_types
    return mock_google, mock_genai, mock_types


def _start_genai_patch():
    """Patch sys.modules so that 'from google import genai' returns a MagicMock."""
    mock_google, mock_genai, mock_types = _build_genai_mocks()
    patcher = patch.dict("sys.modules", {
        "google": mock_google,
        "google.genai": mock_genai,
        "google.genai.types": mock_types,
    })
    patcher.start()
    # Ensure fresh import of llm_gemini so it picks up the mocked modules
    for key in list(sys.modules):
        if "kegal.llm.llm_gemini" in key:
            del sys.modules[key]
    return patcher, mock_genai, mock_types


# ---------------------------------------------------------------------------
# Validation tests (no mock needed — errors raised before google.genai import)
# ---------------------------------------------------------------------------

class TestLlmGeminiValidation(unittest.TestCase):

    def test_missing_model_raises(self):
        from kegal.llm.llm_gemini import LlmGemini
        with self.assertRaises(ValueError) as ctx:
            LlmGemini(api_key="key")
        self.assertIn("model", str(ctx.exception))

    def test_missing_api_key_raises(self):
        from kegal.llm.llm_gemini import LlmGemini
        with self.assertRaises(ValueError) as ctx:
            LlmGemini(model="gemini-2.0-flash")
        self.assertIn("api_key", str(ctx.exception))


# ---------------------------------------------------------------------------
# Unit tests — google.genai fully mocked
# ---------------------------------------------------------------------------

class TestLlmGeminiUnit(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._patcher, cls.mock_genai, cls.mock_types = _start_genai_patch()
        from kegal.llm.llm_gemini import LlmGemini
        cls.LlmGemini = LlmGemini

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()

    def setUp(self):
        # Reset call counts between tests and give each test its own client mock
        self.mock_client = MagicMock()
        type(self).mock_genai.Client.return_value = self.mock_client
        type(self).mock_genai.reset_mock()
        type(self).mock_genai.Client.return_value = self.mock_client

    def _make(self, model="gemini-2.0-flash", api_key="test-key"):
        return self.LlmGemini(model=model, api_key=api_key)

    # --- init ---

    def test_init_creates_genai_client(self):
        inst = self._make(api_key="my-api-key")
        self.mock_genai.Client.assert_called_once_with(api_key="my-api-key")
        self.assertEqual(inst.model, "gemini-2.0-flash")

    def test_init_stores_model(self):
        inst = self._make(model="gemini-1.5-pro")
        self.assertEqual(inst.model, "gemini-1.5-pro")

    # --- _chat_history ---

    def test_chat_history_user_role_preserved(self):
        inst = self._make()
        from kegal.llm.llm_model import LLmMessage
        history = [LLmMessage(role="user", content="hello")]
        inst._chat_history(history)
        call_args = self.mock_types.Content.call_args
        self.assertEqual(call_args.kwargs["role"], "user")

    def test_chat_history_assistant_mapped_to_model(self):
        inst = self._make()
        from kegal.llm.llm_model import LLmMessage
        history = [LLmMessage(role="assistant", content="hi")]
        inst._chat_history(history)
        call_args = self.mock_types.Content.call_args
        self.assertEqual(call_args.kwargs["role"], "model")

    def test_chat_history_dict_input(self):
        inst = self._make()
        history = [{"role": "assistant", "content": "ok"}]
        inst._chat_history(history)
        call_args = self.mock_types.Content.call_args
        self.assertEqual(call_args.kwargs["role"], "model")

    # --- _images_data ---

    def test_images_data_calls_part_from_bytes(self):
        import base64
        from kegal.llm.llm_model import LLMImageData
        inst = self._make()
        img = LLMImageData(media_type="image/jpeg", image_b64=base64.b64encode(b"fake").decode())
        inst._images_data([img])
        self.mock_types.Part.from_bytes.assert_called_once()
        kwargs = self.mock_types.Part.from_bytes.call_args.kwargs
        self.assertEqual(kwargs["mime_type"], "image/jpeg")

    # --- _pdfs_data ---

    def test_pdfs_data_calls_part_from_bytes_with_pdf_mime(self):
        import base64
        from kegal.llm.llm_model import LLMPdfData
        inst = self._make()
        pdf = LLMPdfData(doc_b64=base64.b64encode(b"fakepdf").decode())
        inst._pdfs_data([pdf])
        self.mock_types.Part.from_bytes.assert_called_once()
        kwargs = self.mock_types.Part.from_bytes.call_args.kwargs
        self.assertEqual(kwargs["mime_type"], "application/pdf")

    # --- _tools_data ---

    def test_tools_data_produces_tool_with_declarations(self):
        from kegal.llm.llm_model import LLMTool, LLMStructuredSchema
        inst = self._make()
        tool = LLMTool(
            name="greet",
            description="Return a greeting.",
            parameters={"name": LLMStructuredSchema(type="string", description="Person name")},
            required=["name"],
        )
        inst._tools_data([tool])
        self.mock_types.Tool.assert_called_once()
        declarations = self.mock_types.Tool.call_args.kwargs["function_declarations"]
        self.assertEqual(len(declarations), 1)

    # --- _structured_output_data ---

    def test_structured_output_data_returns_mime_and_schema(self):
        from kegal.llm.llm_model import LLMStructuredOutput, LLMStructuredSchema
        so = LLMStructuredOutput(json_output=LLMStructuredSchema(
            type="object",
            properties={"answer": LLMStructuredSchema(type="string")},
            required=["answer"],
        ))
        result = self.LlmGemini._structured_output_data(so)
        self.assertEqual(result["response_mime_type"], "application/json")
        self.assertIn("response_schema", result)

    # --- complete() response parsing ---

    def _fake_response(self, text=None, tool_name=None, tool_args=None,
                       input_tokens=10, output_tokens=5):
        resp = MagicMock()
        resp.usage_metadata.prompt_token_count = input_tokens
        resp.usage_metadata.candidates_token_count = output_tokens
        part = MagicMock()
        if tool_name:
            part.function_call = MagicMock()
            part.function_call.name = tool_name
            part.function_call.args = tool_args or {}
            part.text = None
        else:
            part.function_call = None
            part.text = text
        resp.candidates = [MagicMock()]
        resp.candidates[0].content.parts = [part]
        return resp

    def test_complete_text_response(self):
        inst = self._make()
        self.mock_client.models.generate_content.return_value = self._fake_response(
            text="The answer is 42."
        )
        result = inst.complete(user_message="What is the answer?")
        self.assertIsNotNone(result.messages)
        self.assertIn("The answer is 42.", result.messages)
        self.assertIsNone(result.tools)
        self.assertIsNone(result.json_output)

    def test_complete_json_response(self):
        inst = self._make()
        self.mock_client.models.generate_content.return_value = self._fake_response(
            text='{"score": 9, "label": "good"}'
        )
        result = inst.complete(user_message="Rate this.")
        self.assertIsNotNone(result.json_output)
        self.assertEqual(result.json_output["score"], 9)
        self.assertIsNone(result.messages)

    def test_complete_tool_call_response(self):
        inst = self._make()
        self.mock_client.models.generate_content.return_value = self._fake_response(
            tool_name="greet", tool_args={"name": "Alice"}
        )
        result = inst.complete(user_message="Say hi to Alice.")
        self.assertIsNotNone(result.tools)
        self.assertEqual(len(result.tools), 1)
        self.assertEqual(result.tools[0].name, "greet")
        self.assertEqual(result.tools[0].parameters["name"], "Alice")

    def test_complete_token_counts(self):
        inst = self._make()
        self.mock_client.models.generate_content.return_value = self._fake_response(
            text="ok", input_tokens=42, output_tokens=7
        )
        result = inst.complete(user_message="hi")
        self.assertEqual(result.input_size, 42)
        self.assertEqual(result.output_size, 7)

    def test_complete_raises_runtime_error_on_api_exception(self):
        inst = self._make()
        self.mock_client.models.generate_content.side_effect = Exception("API error")
        with self.assertRaises(RuntimeError) as ctx:
            inst.complete(user_message="hi")
        self.assertIn("API error", str(ctx.exception))

    def test_complete_passes_system_prompt_in_config(self):
        inst = self._make()
        self.mock_client.models.generate_content.return_value = self._fake_response(text="ok")
        inst.complete(system_prompt="You are helpful.", user_message="hi")
        config_arg = self.mock_types.GenerateContentConfig.call_args
        self.assertIn("system_instruction", config_arg.kwargs)
        self.assertEqual(config_arg.kwargs["system_instruction"], "You are helpful.")

    def test_complete_no_system_prompt_omits_field(self):
        inst = self._make()
        self.mock_client.models.generate_content.return_value = self._fake_response(text="ok")
        inst.complete(user_message="hi")
        config_arg = self.mock_types.GenerateContentConfig.call_args
        self.assertNotIn("system_instruction", config_arg.kwargs)


if __name__ == "__main__":
    unittest.main()
