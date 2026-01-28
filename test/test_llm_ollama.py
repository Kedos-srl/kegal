import unittest
import os

from kegal import LlmOllama
import tests.llm.test_llm as test_llm



OLLAMA_MODEL = ""

class TestOllama(test_llm.TestLLM, unittest.TestCase):

    @staticmethod
    def get_model():
        return LlmOllama(model=os.getenv(OLLAMA_MODEL))

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