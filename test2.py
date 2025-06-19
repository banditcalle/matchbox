import os
from chromadb import PersistentClient

# Config
CHROMA_DIR = os.getenv("CHROMA_DIR", "./.chroma-db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "sharepoint_docs")

# Initialize Chroma client and collection
client = PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(name=COLLECTION_NAME)

# Query all data in the collection
all_data = collection.get(include=["documents", "metadatas", "embeddings"])

print(f"Total records: {len(all_data['ids'])}")
for i, (doc, meta) in enumerate(zip(all_data["documents"], all_data["metadatas"])):
    print(f"\nRecord {i+1}:")
    print("Source:", meta.get("source", "-"))
    print("Chunk index:", meta.get("chunk_index", "-"))
    print("Text snippet:", doc[:200].replace("\n", " "), "…")

