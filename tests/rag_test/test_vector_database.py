from tests.utils.rag_utils import get_chunks_from_chroma
from pathlib import Path

CURENT_DIR = Path(__file__).parent
WINE_DATA_COLLECTION = "wine_data"

if __name__ == '__main__':
    resulst = get_chunks_from_chroma(CURENT_DIR / "vdb",
                                     WINE_DATA_COLLECTION,
                           "sciri una sintesti della produzione italiana degli ultimi anni")
    print(resulst['documents'])