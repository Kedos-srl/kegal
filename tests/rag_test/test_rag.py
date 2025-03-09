from pathlib import Path

from kegal.compile import  compile_form_yaml_file
from kegal.llm.ollama_handler import OllamaHandler

if __name__ == '__main__':
    response = compile_form_yaml_file(Path("rag_test.yml"),
                                 message="scrivi una breve sintesti della produzione vinicola pugliese degli ultimi anni")
    for r in response:
        print(r)

