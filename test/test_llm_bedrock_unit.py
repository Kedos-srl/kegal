"""Unit tests for LlmBedrock — no AWS credentials required (boto3 is mocked)."""
import unittest
from unittest.mock import MagicMock, patch


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
    }


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


if __name__ == "__main__":
    unittest.main()
