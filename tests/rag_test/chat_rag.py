from pathlib import Path
from datetime import datetime

import gradio as gr

from kegal.compile import compile_from_yaml_file
from kegal.graph_utils import update_yml_file_data_history
from shutil import copyfile

from tests.rag_test.questions.questions import CURRENT_DIR

CURRENT_DIR = Path(__file__).parent

TIMESTAMP = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")

CHATS_DIR = CURRENT_DIR / "chats"
CURRENT_CHAT = CHATS_DIR / f"chat_{TIMESTAMP}.yml"

MEMORIES_DIR = CURRENT_DIR / "memories"
CURRENT_MEMORY = MEMORIES_DIR / f"memory_{TIMESTAMP}.json"




def compile_message(message: str):
    responses = compile_from_yaml_file(CURRENT_CHAT,
                                       message=message)
    out_message = ""
    for response in responses:
        response_content = response.response_content
        # graph output validation
        if "validation" in response_content:
            validate = response_content["validation"]
            if not validate:
                out_message = response_content["response_txt"]
        else:
            return "Invalid response content: no validation"

        if response.id == "assistant":
            assistant_message =  response_content["response_txt"]

            updating_message = update_yml_file_data_history(CURRENT_CHAT, responses)
            return assistant_message

    return f"I am unable to answer the question"


def chatbot(message, history=None):
    return compile_message(message)




if __name__ == '__main__':
    copyfile(CURRENT_DIR / "chat_rag.yml", CURRENT_CHAT)

    # gr.ChatInterface(
    #     fn=chatbot,
    #     type="messages"
    # ).launch()
