# Manual: SharePoint CV Ingestion and Deletion in Vector DB

This manual describes how to use `get_cv_share_point.py` to ingest consultant CVs from SharePoint into a Chroma vector database, as well as how to delete outdated or duplicate records from the database.

---

## 1. Prerequisites
- Python 3.8+
- Required packages: `requests`, `msal`, `chromadb`, `openai`, `python-dotenv`
- Environment variables set in your system or a `.env` file:
  - `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` (Azure AD credentials)
  - `HOSTNAME`, `SITE_PATH`, `LIBRARY_NAME`, `TOP_FOLDER`, `FIELD_VALUE` (SharePoint config)
  - `OPENAI_API_KEY` (OpenAI credentials)
  - `CHROMA_DIR`, `COLLECTION_NAME` (ChromaDB config)

---

## 2. Ingesting CVs from SharePoint to ChromaDB

### Overview
`get_cv_share_point.py` connects to a SharePoint document library, traverses folders, and ingests `.docx` CVs into a Chroma vector database. This enables semantic search and matching of consultant profiles to business opportunities.

### Steps
1. **Authentication**: Uses Microsoft Graph API with credentials from the `.env` file.
2. **Folder Traversal**: Recursively searches for `.docx` files in the specified SharePoint library and folders.
3. **Download & Extraction**: Downloads each Word document and extracts its text content.
4. **Chunking**: Splits the text into manageable chunks for embedding.
5. **Embedding**: Uses OpenAI's API to generate vector embeddings for each chunk.
6. **Upsert to ChromaDB**: Stores the embeddings and metadata (file name, folder, etc.) in a persistent Chroma collection.
7. **Manifest Tracking**: Maintains a manifest to avoid redundant processing and enable efficient updates.
8. **Cleanup**: Removes outdated or deleted vectors from the database.

### Result
All consultant CVs are indexed in ChromaDB, ready for fast semantic search and matching.

---

## 3. Deleting Outdated or Duplicate Records

### Automatic Cleanup
- During each ingestion run, the script compares the current SharePoint files to the manifest and removes any vectors in ChromaDB that no longer correspond to files in SharePoint.
- This ensures the vector database only contains up-to-date CVs.

### Manual De-duplication
- Use the `dedupe_chroma.py` script to find and delete duplicate text chunks in the ChromaDB collection.
- The script compares all stored documents and removes any with identical text content.

#### Example Usage:
```bash
python dedupe_chroma.py
```

---

## 4. Troubleshooting
- Ensure all environment variables are set correctly.
- Check for errors in authentication or SharePoint access.
- If the ChromaDB collection grows unexpectedly, run the de-duplication script.

---

## 5. References
- See `get_cv_share_point.py` for the main ingestion logic.
- See `dedupe_chroma.py` for duplicate removal.
- See `manual.md` for additional project documentation.
