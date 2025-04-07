from pathlib import Path

from kegal.tools.chromadb_tools import get_chunks_from_chroma
from tests.utils.rag_utils import create_chroma_collection, add_documents_to_chroma

CURENT_DIR = Path(__file__).parent
WINE_DATA_COLLECTION = "wine_data"


if __name__ == '__main__':
    # create_chroma_collection(CURENT_DIR / "vdb",
    #                          WINE_DATA_COLLECTION)
    # add_documents_to_chroma(CURENT_DIR / "vdb",
    #                         WINE_DATA_COLLECTION,
    #                         CURENT_DIR / "documents" / "Sabettaetal_IJBS_published_2022.pdf")
    chunks = get_chunks_from_chroma(chroma_db_path="vdb",
                           collection_name = WINE_DATA_COLLECTION,
                           message= "scrivi una breve sintesti della produzione vinicola in Puglia",
                         n_results = 3)
    print(chunks)