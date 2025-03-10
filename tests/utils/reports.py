from datetime import datetime
from pathlib import Path


def save_markdown_report(md_dir: Path, content: str):
    # Create timestamp and directory name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create file path and save content
    file_path = md_dir / f"rag_test_{timestamp}.md"
    file_path.write_text(content)
    print(f"File saved to {file_path}")