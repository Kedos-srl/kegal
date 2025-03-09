import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer



def get_chunks_from_chroma(**kwargs):
    chroma_db_path: str = kwargs["chroma_db_path"]
    collection_name: str = kwargs["collection_name"]
    message: str = kwargs["message"]
    n_results: int = kwargs["n_results"]


    if n_results == 0 or n_results > 5:
        n_results = 3

    client = chromadb.PersistentClient(path=str(chroma_db_path))
    if collection_name in client.list_collections():
        # Use SentenceTransformer directly
        model = SentenceTransformer('all-MiniLM-L6-v2')
        message_vector = model.encode([message]).tolist()

        collection = client.get_collection(name=collection_name)

        result =  collection.query(
            query_embeddings=message_vector,
            n_results=n_results
        )

        citations = ""
        for chunk in result["documents"]:
            citations += "\n".join(chunk)
        return citations
    else:
        print(f"Collection {collection_name} does not exists")