import openai
import tiktoken

from ke_llm.llm.llm_handler import LlmHandler


class GptHandler(LlmHandler):
    def __init__(self, model_: str, api_key_: str):
        super().__init__()
        self.model = model_
        self.client = openai.OpenAI(api_key=api_key_)

    def _token_counter(self, prompt: str) -> int:
        encoder = tiktoken.encoding_for_model(self.model)
        return len(encoder.encode(prompt))



    def complete(self, prompt_: str, temperature_: float = 0.5) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_
                    }
                ]
            }],
            temperature=temperature_
        )

        completion = response.choices[0].message.content
        content = self._cleanup_json_string(completion)


        return { "content": content,
                 "input_size": self._token_counter(prompt_),
                 "output_size": self._token_counter(completion) }

