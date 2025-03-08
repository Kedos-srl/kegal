from pathlib import Path

from tests.utils.rag_utils import create_chroma_collection, add_documents_to_chroma

CURENT_DIR = Path(__file__).parent
WINE_DATA_COLLECTION = "wine_data"


if __name__ == '__main__':
    create_chroma_collection(CURENT_DIR / "vdb", WINE_DATA_COLLECTION)
    add_documents_to_chroma(CURENT_DIR / "vdb",
                            WINE_DATA_COLLECTION,
                            CURENT_DIR / "document" / "sensory_complexity_of_italian_wines.pdf")
