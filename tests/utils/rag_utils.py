from pathlib import Path
import pymupdf4llm


def create_chroma_payload(document_path: Path):
    chunks = pymupdf4llm.to_markdown(doc=document_path,page_chunks=True)
    file_name = Path(chunks[0]["metadata"]["file_path"]).stem
    return {
        "documents": [c["text"] for c in chunks],
        "ids": [f"{file_name}_{c['metadata']['page']}" for c in chunks]
    }




