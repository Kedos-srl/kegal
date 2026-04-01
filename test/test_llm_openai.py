import unittest
import os

from kegal.llm import LlmOpenai
from test import test_llm


OPENAI_MODEL = ""
OPENAI_API_KEY = ""

class TestOpenai(test_llm.TestLLM, unittest.TestCase):
    @staticmethod
    def get_model():
        return LlmOpenai(
            model=os.getenv(OPENAI_MODEL),
            api_key=os.getenv(OPENAI_API_KEY)
        )

    def test_chat(self):
        test_llm.llm_chat(self)

    def test_chat_with_history(self):
        test_llm.llm_chat_with_history(self)

    def test_chat_with_image(self):
        test_llm.llm_chat_with_image(self)

    def test_chat_with_pdf(self):
        pass

    def test_tools(self):
        test_llm.llm_tools(self)

    def test_structured_output(self):
        test_llm.llm_structured_output(self)