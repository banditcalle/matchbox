import os
from chromadb import PersistentClient

CHROMA_DIR = os.getenv("CHROMA_DIR")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

client = PersistentClient(path=CHROMA_DIR)
col = client.get_or_create_collection(name=COLLECTION_NAME)

print("Collection count:", col.count())

# Peek a few records (IDs + some metadata) to confirm the new ID scheme
peek = col.peek(limit=100)
for _id, meta in zip(peek["ids"], peek["metadatas"]):
    print(_id, "→", {k: meta.get(k) for k in ["file_name", "folder", "last_modified", "chunk_index"]})
