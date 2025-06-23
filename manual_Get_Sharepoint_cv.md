# Manual: Resume Ingestion and Opportunity Evaluation Pipeline

This manual describes the two main processes in the TalentBridge project:
1. Loading consultant Resume´s from SharePoint into a vector database (ChromaDB) using `get_share_point.py`.
2. Reading sales opportunities from Microsoft Dynamics 365 and evaluating consultant matches using `get_opps.py`.

---

## 1. Loading Resume´s from SharePoint to ChromaDB (`get_share_point.py`)

### Overview
`get_share_point.py` connects to a SharePoint document library, traverses folders, and ingests `.docx` Resume´s into a Chroma vector database. This enables semantic search and matching of consultant profiles to business opportunities.

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
All consultant Resume´s are indexed in ChromaDB, ready for fast semantic search and matching.

---

## 2. Reading Dynamics Opportunities and Evaluating Resume´s (`get_opps.py`)

### Overview
`get_opps.py` connects to Microsoft Dynamics 365, fetches recent sales opportunities, and evaluates the best-matching consultant Resume´s using the vector database. It uses OpenAI GPT to generate enhanced opportunity descriptions and match explanations.

### Steps
1. **Authentication**: Uses MSAL to obtain an access token for Dynamics 365 Web API.
2. **Fetch Opportunities**: Retrieves recent opportunities (name, description, value, etc.) from Dynamics 365.
3. **Resume Matching**:
    - For each opportunity, combines the name and description.
    - Embeds the combined text using OpenAI's API.
    - Queries ChromaDB for the top matching consultant Resume´s based on vector similarity.
    - Calculates match percentages for each resume.
4. **Prompt Generation**: Builds a prompt for OpenAI GPT, including the opportunity details and top resume matches.
5. **AI Enhancement**: Uses GPT to generate an improved opportunity description and a summary of how the matches inform outreach.
6. **Output**: Prints or returns the enhanced description and match results for each opportunity.

### Result
For each sales opportunity, you receive an AI-enhanced description and a list of the best-matching consultant Resume´s, with match percentages, ready for business development and outreach.

---

## Employee and Company Automation (`get_employees.py` & `get_companies.py`)

### Overview
- `get_employees.py` fetches employees from Dynamics 365 and, for each, resolves the company name using `get_companies.py`.
- For each employee, the script can now automatically trigger SharePoint CV ingestion by calling `get_cv_share_point.py`'s `run_ingestion` function, passing the employee name as `FIELD_VALUE` and the company name as `TOP_FOLDER`.
- If the specified company folder is not found in SharePoint, the process logs an error and skips that employee, continuing with the rest.

### Logging Improvements
- All errors and warnings (such as missing folders) are logged to `logs/get_cv_share_point_errors.log`.
- The pipeline is robust: missing folders or other issues do not stop the process, but are logged and skipped.

### Example Workflow
1. Run `get_employees.py` to process all employees:
    - For each employee, the script attempts to ingest their CV from SharePoint using the resolved company folder.
    - If the folder is missing, the error is logged and the script continues.
2. Review `logs/get_cv_share_point_errors.log` for any missing folders or issues.

---

## Logging

All logging output (including errors and warnings) is now written to files in the `logs/` directory:
- `logs/talentbridge.log`: General info and process logs
- `logs/talentbridge_errors.log`: Warnings and errors only

Log file locations are configured via the `.env` file using the variables `LOG_FILE` and `ERROR_LOG_FILE`.

## ChromaDB Directory

All ChromaDB activity and files are stored in the `.chroma-db/` directory, which is ignored by git via `.gitignore`.

## Duplicate and Outdated Data Handling
- The pipeline automatically removes outdated or deleted vectors from ChromaDB during each run.
- Use `dedupe_chroma.py` to remove duplicate text chunks from the vector database.

## Opportunity Processing
- The script `get_opps.py` now skips opportunities that have already been successfully processed, by reading the log file for previously loaded opportunity IDs.
- When a note is created for an opportunity, the note includes:
    - The opportunity name
    - A direct Dynamics URL to the opportunity record
    - The AI-generated match summary
- The log entry for each processed opportunity now includes both the opportunity ID and name for easier traceability.

## Resume Matching Output
- When matching resumes, the returned HTML now includes the source URL (if present in ChromaDB metadata) for each candidate, shown as a clickable link.

---

## Environment Variables
Both scripts require configuration via a `.env` file. Ensure the following variables are set:
- `TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET` (Azure AD credentials)
- `HOSTNAME`, `SITE_PATH`, `LIBRARY_NAME`, `TOP_FOLDER`, `FIELD_VALUE` (SharePoint config)
- `OPENAI_API_KEY` (OpenAI credentials)
- `CHROMA_DIR`, `COLLECTION_NAME` (ChromaDB config)
- `DYNAMICS_RESOURCE` (Dynamics 365 instance URL)

---

## Typical Workflow
1. Run `get_share_point.py` to ingest and index all consultant Resume´s from SharePoint into ChromaDB.
2. Run `get_opps.py` to fetch new opportunities from Dynamics 365 and evaluate the best consultant matches for each.

This enables a seamless, AI-powered workflow for matching consultant skills to business needs.
