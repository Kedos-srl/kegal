"""Unit tests for LlmBedrock — no AWS credentials required (boto3 is mocked)."""
import json
import unittest
from unittest.mock import MagicMock, patch

from kegal.llm.llm_model import LLMStructuredOutput, LLMStructuredSchema, LLMTool


def _make_bedrock(model="test-model", region="us-east-1"):
    """Return a LlmBedrock instance with a mocked boto3 client."""
    with patch("boto3.client") as mock_boto3:
        mock_boto3.return_value = MagicMock()
        from kegal.llm.llm_bedrock import LlmBedrock
        instance = LlmBedrock(model=model, aws_region_name=region)
    return instance


def _fake_converse_response(text="ok"):
    return {
        "usage": {"inputTokens": 5, "outputTokens": 3},
        "output": {"message": {"content": [{"text": text}]}},
        "stopReason": "end_turn",
    }


def _fake_structured_response(payload, stop_reason="end_turn"):
    return {
        "usage": {"inputTokens": 5, "outputTokens": 3},
        "output": {"message": {"content": [{"text": json.dumps(payload)}]}},
        "stopReason": stop_reason,
    }


def _structured_output():
    return LLMStructuredOutput(
        json_output=LLMStructuredSchema(
            type="object",
            properties={"answer": {"type": "string"}},
            required=["answer"],
        )
    )


def _last_converse_body(bedrock):
    """Return the kwargs of the most recent client.converse(**body) call."""
    return bedrock.client.converse.call_args.kwargs


class TestLlmBedrockUnit(unittest.TestCase):

    def test_close_method_exists(self):
        """LlmBedrock must expose close() so Compiler.close() can call it."""
        from kegal.llm.llm_bedrock import LlmBedrock
        self.assertTrue(callable(getattr(LlmBedrock, "close", None)))

    def test_complete_does_not_close_client(self):
        """complete() must NOT close the boto3 client — it must stay reusable."""
        b = _make_bedrock()
        b.client.converse.return_value = _fake_converse_response()
        b.complete(user_message="hello")
        b.client.close.assert_not_called()

    def test_multiple_complete_calls_reuse_client(self):
        """The same boto3 client must serve multiple complete() calls without error."""
        b = _make_bedrock()
        b.client.converse.return_value = _fake_converse_response()
        b.complete(user_message="first")
        b.complete(user_message="second")
        self.assertEqual(b.client.converse.call_count, 2)
        b.client.close.assert_not_called()

    def test_close_calls_client_close(self):
        """LlmBedrock.close() must delegate to the underlying boto3 client."""
        b = _make_bedrock()
        b.close()
        b.client.close.assert_called_once()

    def test_missing_model_raises(self):
        """Constructing without 'model' must raise ValueError."""
        with patch("boto3.client"):
            from kegal.llm.llm_bedrock import LlmBedrock
            with self.assertRaises(ValueError):
                LlmBedrock(aws_region_name="us-east-1")

    def test_missing_region_raises(self):
        """Constructing without 'aws_region_name' must raise ValueError."""
        with patch("boto3.client"):
            from kegal.llm.llm_bedrock import LlmBedrock
            with self.assertRaises(ValueError) as ctx:
                LlmBedrock(model="test-model")
        self.assertIn("aws_region_name", str(ctx.exception))

    def test_complete_returns_response_with_text(self):
        """complete() must parse text content into LLmResponse.messages."""
        b = _make_bedrock()
        b.client.converse.return_value = _fake_converse_response("hello world")
        resp = b.complete(user_message="hi")
        self.assertIsNotNone(resp.messages)
        self.assertIn("hello world", resp.messages)
        self.assertEqual(resp.input_size, 5)
        self.assertEqual(resp.output_size, 3)

    # --- Native structured output --------------------------------------------

    def test_structured_output_sets_output_config(self):
        """structured_output must produce a native outputConfig, not a forced tool."""
        b = _make_bedrock()
        b.client.converse.return_value = _fake_structured_response({"answer": "42"})
        b.complete(user_message="q", structured_output=_structured_output())

        body = _last_converse_body(b)
        js = body["outputConfig"]["textFormat"]["structure"]["jsonSchema"]
        self.assertEqual(body["outputConfig"]["textFormat"]["type"], "json_schema")
        self.assertIn("additionalProperties", js["schema"])
        self.assertIn('"additionalProperties": false', js["schema"])
        # no forced tool-choice emulation any more
        self.assertNotIn("toolConfig", body)

    def test_structured_output_parses_json(self):
        """A valid JSON text block becomes json_output; messages stays empty."""
        b = _make_bedrock()
        b.client.converse.return_value = _fake_structured_response({"answer": "42"})
        resp = b.complete(user_message="q", structured_output=_structured_output())
        self.assertEqual(resp.json_output, {"answer": "42"})
        self.assertIsNone(resp.messages)

    def test_structured_output_freetext_raises(self):
        """Free-text instead of JSON must raise, not silently return None."""
        b = _make_bedrock()
        b.client.converse.return_value = {
            "usage": {"inputTokens": 5, "outputTokens": 3},
            "output": {"message": {"content": [{"text": "sorry, here is my answer"}]}},
            "stopReason": "end_turn",
        }
        with self.assertRaises(RuntimeError):
            b.complete(user_message="q", structured_output=_structured_output())

    def test_structured_output_malformed_stopreason_raises(self):
        """stopReason=malformed_model_output must raise."""
        b = _make_bedrock()
        b.client.converse.return_value = _fake_structured_response(
            {"answer": "42"}, stop_reason="malformed_model_output"
        )
        with self.assertRaises(RuntimeError):
            b.complete(user_message="q", structured_output=_structured_output())

    def test_tools_and_structured_output_coexist(self):
        """Real tools and structured output must both land in the body, no toolChoice."""
        b = _make_bedrock()
        b.client.converse.return_value = _fake_structured_response({"answer": "42"})
        tool = LLMTool(
            name="search",
            description="search the web",
            parameters={"q": LLMStructuredSchema(type="string")},
            required=["q"],
        )
        b.complete(
            user_message="q",
            tools_data=[tool],
            structured_output=_structured_output(),
        )
        body = _last_converse_body(b)
        self.assertIn("toolConfig", body)
        self.assertIn("outputConfig", body)
        self.assertNotIn("toolChoice", body["toolConfig"])


if __name__ == "__main__":
    unittest.main()
