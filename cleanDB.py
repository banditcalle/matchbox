import os
from chromadb import PersistentClient

CHROMA_DIR      = os.getenv("CHROMA_DIR")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

# Open the store
client = PersistentClient(path=CHROMA_DIR)

# Delete the named collection (drops all its vectors)
client.delete_collection(name=COLLECTION_NAME)

# (Optional) Confirm it’s gone
print("Remaining collections:", [c.name for c in client.list_collections()])

# emtpty ingetst_manifest.json
with open("ingest_manifest.json", "w") as f:
    f.write("{}")

