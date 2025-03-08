from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
import pymupdf4llm


class ChromaPayload:
    def __init__(self, document_path: Path):
        # Use SentenceTransformer directly instead of ChromaDB's default embedding
        model = SentenceTransformer('all-MiniLM-L6-v2')
        chunks = pymupdf4llm.to_markdown(doc=document_path, page_chunks=True)
        file_name = Path(chunks[0]["metadata"]["file_path"]).stem

        self.documents = [c["text"] for c in chunks]
        self.ids = [f"{file_name}_{c['metadata']['page']}" for c in chunks]
        # Convert to list of embeddings
        self.vectors = model.encode(self.documents).tolist()


def create_chroma_collection(chroma_db_path: Path, collection_name: str):
    client = chromadb.PersistentClient(path=str(chroma_db_path))
    if collection_name not in client.list_collections():
        client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    else:
        print(f"Collection {collection_name} already exists")


def add_documents_to_chroma(chroma_db_path: Path, collection_name: str, document_path: Path):
    client = chromadb.PersistentClient(path=str(chroma_db_path))
    if collection_name in client.list_collections():
        payload = ChromaPayload(document_path)

        collection = client.get_collection(name=collection_name)
        collection.add(documents=payload.documents,
                       ids=payload.ids,
                       embeddings=payload.vectors)
    else:
        print(f"Collection {collection_name} does not exists")


