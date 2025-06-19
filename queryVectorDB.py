import os
import sys
import pandas as pd
from chromadb import PersistentClient

# ── CONFIGURE VIA ENV VARIABLES ─────────────────────────────────────────────────
CHROMA_DIR      = os.getenv("CHROMA_DIR")       # e.g. "./chroma_store"
COLLECTION_NAME = os.getenv("COLLECTION_NAME")   # e.g. "sharepoint_docs"
# ─────────────────────────────────────────────────────────────────────────────────

if not CHROMA_DIR or not COLLECTION_NAME:
    raise RuntimeError("Make sure CHROMA_DIR and COLLECTION_NAME are set in your environment.")

# 1) Open the existing PersistentClient (on‐disk)
client = PersistentClient(path=CHROMA_DIR)

# 2) List all collections to confirm what’s in CHROMA_DIR
print("Available collections in this Chroma directory:")
for coll in client.list_collections():
    print("  -", coll)

# 3) Load the target collection by name (will error if it doesn't exist)
collection = client.get_collection(name=COLLECTION_NAME)
total_count = collection.count()
print(f"\nLoaded collection '{COLLECTION_NAME}'. Total vector count: {total_count}")

# 4) If the collection is empty, exit
if total_count == 0:
    print("The collection is empty. No records to inspect.")
    sys.exit(0)

# 5) Let’s test a few different include‐lists to see what keys come back.
test_includes = [
    ["documents"],
    ["embeddings"],
    ["metadatas"],
    ["documents", "metadatas"],
    ["documents", "embeddings", "metadatas"],
    ["distances"],
    ["uris"],
]

print("\n—— Testing various include‐lists ————————————————————————————————")
for inc in test_includes:
    try:
        resp = collection.get(include=inc)
        print(f"include={inc}  ⇒  returned keys: {list(resp.keys())}")
    except Exception as e:
        print(f"include={inc}  ⇒  ERROR: {e}")

# 6) Once you identify a working include combination, set it here:
#    (for example, if ["documents","metadatas","embeddings"] worked above, use that)
inc_choice = ["documents", "metadatas", "embeddings"]

# 7) Fetch one sample record at index 0 to inspect its fields
sample_resp = collection.get(include=inc_choice)
# We already checked that total_count > 0, so index 0 must exist
sample_record = {key: sample_resp[key][0] for key in inc_choice}

print(f"\nSample record at index 0 using include={inc_choice}:")
for k, v in sample_record.items():
    tname = type(v).__name__
    if isinstance(v, list):
        detail = f"list(len={len(v)})"
    elif isinstance(v, dict):
        detail = f"dict(keys={list(v.keys())})"
    else:
        detail = repr(v)
    print(f"  - {k} ({tname}): {detail}")

# 8) Load the entire collection into a DataFrame using the same include
print("\nLoading the entire collection into a DataFrame now...")
full_resp = collection.get(include=inc_choice)

docs  = full_resp.get("documents", [])
embs  = full_resp.get("embeddings", [])
metas = full_resp.get("metadatas", [])

rows = []
for idx in range(len(docs)):
    row = {
        "document": docs[idx],
        "embedding": embs[idx],
        **(metas[idx] if isinstance(metas[idx], dict) else {})
    }
    rows.append(row)

df = pd.DataFrame(rows)

print("\nResulting DataFrame columns:")
print(df.columns.tolist())

print("\nFirst 5 rows of the DataFrame:")
print(df.head())

# 9) (Optional) Save to CSV if you want:
# df.to_csv("all_chroma_data.csv", index=False)
