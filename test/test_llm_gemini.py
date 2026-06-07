"""Integration tests for LlmGemini — requires GEMINI_API_KEY env var and google-genai installed.

Run with:
    export GEMINI_API_KEY="your-key"
    conda run -n red python -m pytest test/test_llm_gemini.py -v
"""
import os
import unittest

from test import test_llm

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

_SKIP = not GEMINI_API_KEY


@unittest.skipIf(_SKIP, "GEMINI_API_KEY not set — skipping live Gemini tests")
class TestGemini(test_llm.TestLLM, unittest.TestCase):

    @staticmethod
    def get_model():
        from kegal.llm.llm_gemini import LlmGemini
        return LlmGemini(model=GEMINI_MODEL, api_key=GEMINI_API_KEY)

    def test_chat(self):
        test_llm.llm_chat(self)

    def test_chat_with_history(self):
        test_llm.llm_chat_with_history(self)

    def test_chat_with_image(self):
        test_llm.llm_chat_with_image(self)

    def test_chat_with_pdf(self):
        test_llm.llm_chat_with_pdf(self)

    def test_tools(self):
        test_llm.llm_tools(self)

    def test_structured_output(self):
        test_llm.llm_structured_output(self)


if __name__ == "__main__":
    unittest.main()
