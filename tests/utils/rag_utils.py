from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from llama_index.core.node_parser import SentenceSplitter
import pymupdf4llm


class ChromaPayload:
    def __init__(self, document_path: Path):
        # Use SentenceTransformer directly instead of ChromaDB's default embedding
        model = SentenceTransformer('all-MiniLM-L6-v2')
        pages = pymupdf4llm.to_markdown(doc=document_path, page_chunks=True)
        file_name = Path(pages[0]["metadata"]["file_path"]).stem

        splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=20)

        self.documents = []
        self.ids = []
        self.embeddings = []
        for page in pages:
            page_text = page["text"]
            page_id = f"{file_name}_p{page['metadata']['page']}"
            chunks = splitter.split_text(page_text)
            for i, c in enumerate(chunks):
                self.documents.append(c)
                self.ids.append(f"{page_id}_c{i}")
                self.embeddings.append(model.encode(c).tolist())



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
                       embeddings=payload.embeddings)
    else:
        print(f"Collection {collection_name} does not exists")


