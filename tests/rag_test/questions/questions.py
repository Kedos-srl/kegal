from pathlib import Path

import yaml

CURRENT_DIR = Path(__file__).parent

def load_question_file_en():
    file_path = CURRENT_DIR / "questions_en.yml"
    return yaml.safe_load(file_path.read_text())

