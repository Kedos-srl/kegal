from ollama import Client

from kegal.llm.llm_handler import LlmHandler


class OllamaHandler(LlmHandler):
    def __init__(self, model_: str, host_: str = 'http://localhost:11434'):
        print(model_, host_)
        self.model = model_
        self.client = Client(
            host=host_
        )

    def complete(self, prompt_: str, temperature_: float = 0.5) -> dict:
        response =  self.client.chat(
            model=self.model,
            messages=[{
                "role": "user",
                "content": prompt_
            }],
            options={"temperature": temperature_}
        )

        completion = response['message']["content"]
        content = self._cleanup_json_string(completion)

        return { "content": content,
                "input_size": response['prompt_eval_count'],
                "output_size": response['eval_count'] }

