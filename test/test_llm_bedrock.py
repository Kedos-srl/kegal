import unittest
import os

from kegal import LlmBedrock
import tests.llm.test_llm as test_llm

from pathlib import Path
from dotenv import load_dotenv

TEST_DIR = Path(__file__).parent
print(TEST_DIR)
load_dotenv(dotenv_path=TEST_DIR /  "aws.env")


AWS_MODEL = ""
AWS_REGION_NAME = ""
AWS_ACCESS_KEY = ""
AWS_SECRET_KEY = ""


class TestBedrock(test_llm.TestLLM, unittest.TestCase):

    @staticmethod
    def get_model():
        return LlmBedrock(
            model=os.getenv(AWS_MODEL),
            aws_region_name=os.getenv(AWS_REGION_NAME),
            aws_access_key=os.getenv(AWS_ACCESS_KEY),
            aws_secret_key=os.getenv(AWS_SECRET_KEY)
        )

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