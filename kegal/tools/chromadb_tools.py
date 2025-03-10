import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer
import torch

model = SentenceTransformer('all-MiniLM-L6-v2')


def get_chunks_from_chroma(**kwargs):
    chroma_db_path: str = kwargs["chroma_db_path"]
    collection_name: str = kwargs["collection_name"]
    message: str = kwargs["message"]
    n_results: int = kwargs["n_results"]

    if n_results == 0 or n_results > 5:
        n_results = 3

    client = chromadb.PersistentClient(path=str(chroma_db_path))
    if collection_name in client.list_collections():
        try:
            # Try to use GPU if available
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

            # Initialize model with specific device and lower memory usage
            try:
                model.to(device)
            except RuntimeError:
                # If GPU memory error occurs, fall back to CPU
                print("GPU memory insufficient, falling back to CPU")
                device = torch.device('cpu')
                model.to(device)

            # Process input in a memory-efficient way
            with torch.no_grad():  # Disable gradient calculation
                message_vector = model.encode([message],
                                              device=device,
                                              show_progress_bar=False,
                                              convert_to_tensor=True)
                message_vector = message_vector.cpu().numpy().tolist()

            collection = client.get_collection(name=collection_name)
            result = collection.query(
                query_embeddings=message_vector,
                n_results=n_results
            )

            # Clear GPU memory if it was used
            if device.type == 'cuda':
                torch.cuda.empty_cache()

            citations = ""
            for chunk in result["documents"]:
                citations += "\n".join(chunk)
            return citations
        except Exception as e:
            print(f"Error during embedding generation: {str(e)}")
            return ""
    else:
        print(f"Collection {collection_name} does not exist")
        return ""