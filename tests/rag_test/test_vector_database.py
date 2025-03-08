from pathlib import Path

from kegal.tools.chromadb_tools import get_chunks_from_chroma

CURENT_DIR = Path(__file__).parent
WINE_DATA_COLLECTION = "wine_data"

if __name__ == '__main__':
    chunks = get_chunks_from_chroma(chroma_db_path = "vdb",
                                    collection_name=WINE_DATA_COLLECTION,
                                    message="sciri una sintesti della produzione italiana degli ultimi anni",
                                    n_results=3)
    print(chunks)