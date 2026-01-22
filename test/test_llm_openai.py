import unittest
import os

from kegal import LllmOpenai
import tests.llm.test_llm as test_llm

from pathlib import Path
from dotenv import load_dotenv

TEST_DIR = Path(__file__).parent
print(TEST_DIR)
load_dotenv(dotenv_path=TEST_DIR /  "openai.env")


class TestOpenai(test_llm.TestLLM, unittest.TestCase):
    @staticmethod
    def get_model():
        return LllmOpenai(
            model=os.getenv("OPENAI_MODEL"),
            api_key=os.getenv("OPENAI_API_KEY")
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