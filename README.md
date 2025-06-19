# TalentBridge SharePoint Ingestion Pipeline

This project provides a pipeline to ingest, process, and embed Word documents from a SharePoint document library into a Chroma vector database for semantic search and retrieval. It leverages Microsoft Graph API, OpenAI embeddings, and ChromaDB for efficient document management and search.

## Features
- **Microsoft Graph API Integration:** Authenticates and fetches files and metadata from SharePoint document libraries.
- **Automated Folder Traversal:** Recursively traverses SharePoint folders to locate and process `.docx` files.
- **Document Extraction:** Downloads and extracts text from Word documents.
- **Text Chunking:** Splits documents into manageable text chunks for embedding.
- **OpenAI Embeddings:** Generates vector embeddings for each text chunk using OpenAI's API.
- **Chroma Vector Store:** Stores embeddings and metadata in a persistent ChromaDB collection.
- **Manifest Tracking:** Maintains an ingestion manifest to avoid redundant processing and enable efficient updates.
- **Cleanup:** Removes deleted or outdated vectors from the database.

## Setup
1. **Install Dependencies:**
   - Python 3.8+
   - `pip install -r requirements.txt` (requirements: `requests`, `msal`, `python-docx`, `openai`, `chromadb`, `fnmatch`)
2. **Configure Credentials:**
   - Set your Azure AD `TENANT_ID`, `CLIENT_ID`, and `CLIENT_SECRET` in `Test.py`.
   - Set your `OPENAI_API_KEY` as an environment variable.
3. **Edit Config:**
   - Update `HOSTNAME`, `SITE_PATH`, `LIBRARY_NAME`, `TOP_FOLDER`, and `FIELD_VALUE` in `Test.py` to match your SharePoint structure.

## Usage
Run the ingestion script:
```powershell
python Test.py
```
- The script will authenticate, locate the specified folders, process `.docx` files, extract and embed their content, and upsert the data into ChromaDB.
- A manifest file (`ingest_manifest.json`) tracks processed files and chunk counts for incremental updates.

## File Overview
- `Test.py` — Main ingestion pipeline script.
- `ingest_manifest.json` — Tracks processed files and chunk counts.
- `requirements.txt` — Python dependencies for the project.
- `README.md` — Project documentation and usage instructions.
- `app.py` — Utility for reading Excel files and extracting consultant data.
- `get_opps.py` — Fetches sales opportunities from Microsoft Dynamics 365, matches them with top consultant resumes using semantic search, and generates enhanced opportunity descriptions with match percentages using OpenAI GPT.
- `match_prompts.py` — Contains logic for embedding, searching, and matching opportunities to consultant resumes, and generating enhanced descriptions.
- `getSharePoint.py`, `get_share_point.py`, `test2.py`, `cv_processor.py`, `dedupe_chroma.py`, `queryVectorDB.py` — Additional scripts for SharePoint, data processing, deduplication, querying, and matching.
- `get_employees.py` — Fetches employees from Dynamics 365, prints their name, email, and resolves their company name using `get_companies.py`.
- `get_companies.py` — Fetches and resolves company (subsidiary) labels from Dynamics 365 option sets.
- `Infile_temp/AvailableConsultants.xlsx` — Example input file (not processed by the pipeline).
- `__pycache__/` — Python bytecode cache directory.

## Customization
- Adjust chunk size and overlap in `chunk_text()` as needed.
- Modify metadata fields or embedding model as required.

## License
This project is for internal use. Please ensure you comply with your organization's data and API usage policies.

# banditcalle-TalentBridge
Bildlig koppling mellan konsulternas kompetens och affärsbehov.
https://agroup.sharepoint.com/sites/CV/Delade%20dokument/Forms/AllItems.aspx?viewid=1451e3ba%2D9c9e%2D49df%2Db980%2D5455addd4a46&newTargetListUrl=%2Fsites%2FCV%2FDelade%20dokument&viewpath=%2Fsites%2FCV%2FDelade%20dokument%2FForms%2FAllItems%2Easpx

## Employee Fetch Example
To print all employees with their company names:
```powershell
python get_employees.py
```
This will output each consultant's ID, name, email, subsidiary value, and the resolved company name.