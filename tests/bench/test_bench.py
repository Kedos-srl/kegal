# Benchmark or-bench
# https://arxiv.org/pdf/2405.20947

from pathlib import Path
from datasets import load_dataset
from kegal.compile import compile_from_yaml_file

general_report = {
    "output_failed": 0,
    "output_ok": 0,
    "validation_failed": 0,
    "validation_ok": 0
}

result = {
    "deception": 0,
    "harassment": 0,
    "harmful": 0,
    "hate": 0,
    "illegal": 0,
    "privacy": 0,
    "self-harm": 0,
    "sexual": 0,
    "unethical":0,
    "violence":0
}
category = {
    "deception": 0,
    "harassment": 0,
    "harmful": 0,
    "hate": 0,
    "illegal": 0,
    "privacy": 0,
    "self-harm": 0,
    "sexual": 0,
    "unethical":0,
    "violence":0
}

this_folder = Path(__file__).resolve().parent

ds = load_dataset("bench-llm/or-bench", "or-bench-hard-1k")
for sample in ds['train']:
    print(f"Prompt: {sample['prompt']}")
    response = compile_from_yaml_file(Path(this_folder / "or-bench-hard-1k.yml"), message=sample['prompt'])
    for r in response:
        response_content = r.response_content
        print(response_content)