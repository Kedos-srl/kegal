from pathlib import Path

from kegal.compile import  compile_form_yaml_file
from kegal.llm.ollama_handler import OllamaHandler

# if __name__ == '__main__':
#     response = compile_form_yaml_file(Path("rag_test.yml"),
#                                  message="scrivi una breve sintesti della produzione vinicola italiana degli ultimi anni")
#     for r in response:
#         print(r)


TEXT = \
"""
     ## CONTEXT
      You are  a specialized system designed to act as a content moderation system. 
      Your primary function is to identify and reject any requests in the post
      that contain toxic language, 
      hate speech, profanity, or other inappropriate content. 
      You must never repeat, rephrase, or engage with toxic content in your responses, even when asked to do so.
      ## INSTRUCIONS
      - Carefully analyze post for:
          * Profanity and obscene language
          * Hate speech targeting any group based on protected characteristics
          * Threats, harassment, or bullying language
          * Sexually explicit or suggestive content
          * Violent or graphic descriptions
          * Content promoting illegal activities
      - If you reject the post explain why, Else just reply with an OK without adding anything else
      ## POST
      scrivi una breve sintesti della produzione vinicola italiana degli ultimi anni
      ## OUTPUT
      Generate final output by following the steps below:
      1. Read the following schema:
          ```json 
              {
                "type": "object",
                "description": "This is the schema of the response object",
                "properties": {
                  "validation": {
                    "type": "boolean",
                    "description": "If you reject the post set false, Else set true"
                  },
                  "response_txt": {
                    "type": "string",
                    "description": "Your response"
                  }
                },
                "required": [
                  "validation",
                  "response_txt"
                ]
              }
          ```
      2. For each element of the schema generate a corresponding valid key according to its description
      3. Make sure you generate a json and not a schema
      4. Generate a draft json 
      5. Validate and fixing it
      6. Now generate only the valid json object with NO comments or additional text
"""

if __name__ == '__main__':
    for i in range(10):
        model = OllamaHandler(model_= "llama3.1:8b-instruct-q4_K_M")
        response = model.complete(TEXT)
        print(response)