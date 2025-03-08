from pathlib import Path

from tests.utils.rag_utils import create_chroma_payload

CURENT_DIR = Path(__file__).parent

if __name__ == '__main__':
    chunks = create_chroma_payload(CURENT_DIR / 'document' / 'sensory_complexity_of_italian_wines.pdf')
    # for chunk in chunks:
    #     print(chunk["id"])