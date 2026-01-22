import json
import unittest

from abc import abstractmethod, ABC

from kegal.tests import prompts


def llm_chat(utest):
    print("Test chat")

    model = utest.get_model()

    prompt = prompts.get_chat_prompts()

    response = model.complete(
        system_prompt=prompt["system_prompt"],
        user_message=prompt["user_message"]
    )
    utest.assertTrue(len(response.messages) != 0)
    utest.assertTrue(response.input_size > 0)
    utest.assertTrue(response.output_size > 0)
    for message in response.messages:
        print(message)


def llm_chat_with_history(utest):
    print("Test chat with history")

    model = utest.get_model()

    prompt = prompts.get_chat_prompt_with_history()

    response = model.complete(
            system_prompt=prompt["system_prompt"],
            user_message=prompt["user_message"],
            chat_history=prompt["chat_history"]
    )
    utest.assertTrue(response.messages is not None)
    utest.assertTrue(len(response.messages) != 0)
    utest.assertTrue(response.input_size > 0)
    utest.assertTrue(response.output_size > 0)
    for message in response.messages:
        print(message)


def llm_chat_with_image(utest):
    print("Test multimodal chat with image")

    model = utest.get_model()

    prompt = prompts.get_image_prompts()

    response = model.complete(
        system_prompt=prompt["system_prompt"],
        user_message=prompt["user_message"],
        imgs_b64=prompt["images"]
    )
    utest.assertTrue(len(response.messages) != 0)
    utest.assertTrue(response.input_size > 0)
    utest.assertTrue(response.output_size > 0)
    for message in response.messages:
        print(message)


def llm_chat_with_pdf(utest):
    print("Test multimodal chat with pdf")

    model = utest.get_model()

    prompt = prompts.get_pdf_prompts()

    response = model.complete(
        system_prompt=prompt["system_prompt"],
        user_message=prompt["user_message"],
        pdfs_b64=prompt["pdfs"]
    )
    utest.assertTrue(len(response.messages) != 0)
    utest.assertTrue(response.input_size > 0)
    utest.assertTrue(response.output_size > 0)
    for message in response.messages:
        print(message)


def llm_tools(utest):
    print("Test tools")

    model = utest.get_model()

    prompt = prompts.get_tools_prompt()

    response = model.complete(
        user_message=prompt["user_message"],
        tools_data=prompt["tools"],
        temperature=0.0
    )
    utest.assertTrue(response.tools is not None)
    utest.assertTrue(response.input_size > 0)
    utest.assertTrue(response.output_size > 0)
    for tool in response.tools:
        print(tool.model_dump())


def llm_structured_output(utest):
    print("Test Structured Output")

    model = utest.get_model()

    prompt = prompts.get_structured_output_prompt()

    response = model.complete(
        system_prompt=prompt["system_prompt"],
        user_message=prompt["user_messages"][0],
        structured_output=prompt["structured_output"],
        temperature=0.5
    )
    utest.assertTrue(response.json_output is not None)
    utest.assertTrue(response.input_size > 0)
    utest.assertTrue(response.output_size > 0)
    print(f"Response 1: {json.dumps(response.json_output, indent=2)}")

    response = model.complete(
        system_prompt=prompt["system_prompt"],
        user_message=prompt["user_messages"][1],
        structured_output=prompt["structured_output"],
        temperature=0.5
    )
    utest.assertTrue(response.json_output is not None)
    utest.assertTrue(response.input_size > 0)
    utest.assertTrue(response.output_size > 0)
    print(f"Response 2: {json.dumps(response.json_output, indent=2)}")


class TestLLM(ABC):

    @staticmethod
    @abstractmethod
    def get_model():
        pass

    @abstractmethod
    def test_chat(self):
        pass

    @abstractmethod
    def test_chat_with_history(self):
        pass

    @abstractmethod
    def test_chat_with_image(self):
        pass

    @abstractmethod
    def test_chat_with_pdf(self):
        pass

    @abstractmethod
    def test_tools(self):
        pass

    @abstractmethod
    def test_structured_output(self):
        pass



