from chromadb import PersistentClient

CHROMA_DIR      = "./.chroma-db"
COLLECTION_NAME = "sharepoint_docs"

# 1. Open your DB
client     = PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(name=COLLECTION_NAME)

# 2. Pull back all documents + their IDs
data = collection.get(include=["documents", "metadatas"])
ids  = data["ids"]
docs = data["documents"]

# 3. Find duplicates by exact text match
seen     = {}
dupe_ids = []
for doc_id, text in zip(ids, docs):
    if text in seen:
        dupe_ids.append(doc_id)
    else:
        seen[text] = doc_id

# 4. Delete any duplicates
if dupe_ids:
    print(f"Deleting {len(dupe_ids)} duplicate chunks…")
    collection.delete(ids=dupe_ids)
else:
    print("No duplicates found.")
