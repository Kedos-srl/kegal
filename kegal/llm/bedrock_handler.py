from kegal.llm.llm_handler import LlmHandler


import boto3
from botocore.exceptions import ClientError

class BedrockHandler(LlmHandler):
    def __init__(self, model_: str, region_name_: str, access_key_: str, secret_key_: str):
        super().__init__()
        self.model = model_
        self.client = boto3.client(service_name='bedrock-runtime',
                                   region_name=region_name_,
                                   aws_access_key_id=access_key_,
                                   aws_secret_access_key=secret_key_)


    def complete(self, prompt_: str, temperature_: float = 0.5) -> dict:
        try:
            response = self.client.converse(
                modelId=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt_}],
                    }
                ],
                inferenceConfig={"temperature": temperature_}
            )


            usage = response["usage"]
            content = response["output"]["message"]["content"][0]["text"]


            return { "content": self._cleanup_json_string(content),
                     "input_size": usage["inputTokens"] ,
                     "output_size":  usage["outputTokens"]}

        except (ClientError, Exception) as e:
            print(f"ERROR: Can't invoke '{self.model}'. Reason:\n {e}")
            exit(1)
