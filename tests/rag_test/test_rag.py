from pathlib import Path

from kegal.compile import  compile_form_yaml_file
from kegal.llm.ollama_handler import OllamaHandler




if __name__ == '__main__':
    response = compile_form_yaml_file(Path("rag_test.yml"),
                                 message="scrivi una breve sintesti della produzione vinicola pugliese degli ultimi anni")
    for r in response:
        node_id = r.id
        prompt_size = r.prompt_size
        response_size = r.response_size
        response_content = r.response_content
        print(f"NODE[{node_id}]")
        print(f"- prompt size: {prompt_size}")
        print(f"- response size: {response_size}")

        print(f"- response content:")
        if "validation" in response_content:
            validation = response_content["validation"]
            print(f"validation: {validation}")
        else:
            print("Invalid response content: no validation")

        if "response_txt" in response_content:
            print(response_content["response_txt"])
        elif "response_tool" in r:
            print(response_content["response_tool"])
        elif "response_obj" in r:
            print(response_content["response_obj"])
        else:
            print("Invalid response content: no response")

