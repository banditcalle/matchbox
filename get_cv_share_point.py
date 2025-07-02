import os
import json
import requests
from io import BytesIO
from docx import Document
from msal import ConfidentialClientApplication
import fnmatch
import openai
from chromadb import PersistentClient
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import logging

# --- Logging setup ---
LOG_FILE = os.path.join("logs", "get_cv_sharepoint.log")
ERROR_LOG_FILE = os.path.join("logs", "get_cv_share_point_errors.log")

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
error_handler = logging.FileHandler(ERROR_LOG_FILE, mode="a", encoding="utf-8")
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(error_handler)
logger = logging.getLogger(__name__)

# ─── Load environment variables ──────────────────────────────────────────────────
load_dotenv()

TENANT_ID       = os.getenv("TENANT_ID")
CLIENT_ID       = os.getenv("CLIENT_ID")
CLIENT_SECRET   = os.getenv("CLIENT_SECRET")

HOSTNAME        = os.getenv("HOSTNAME")
SITE_PATH       = os.getenv("SITE_PATH")
LIBRARY_NAME    = os.getenv("LIBRARY_NAME")
TOP_FOLDER      = os.getenv("TOP_FOLDER")
FIELD_VALUE     = os.getenv("FIELD_VALUE")

openai.api_key  = os.getenv("OPENAI_API_KEY")
CHROMA_DIR      = os.getenv("CHROMA_DIR")
MANIFEST_PATH   = os.getenv("MANIFEST_PATH")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
# ──────────────────────────────────────────────────────────────────────────────────

# Safety checks
try:
    if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET, HOSTNAME, SITE_PATH,
                LIBRARY_NAME, TOP_FOLDER, FIELD_VALUE, openai.api_key,
                CHROMA_DIR, MANIFEST_PATH, COLLECTION_NAME]):
        missing = [k for k,v in {
            "TENANT_ID":TENANT_ID, "CLIENT_ID":CLIENT_ID, "CLIENT_SECRET":CLIENT_SECRET,
            "HOSTNAME":HOSTNAME, "SITE_PATH":SITE_PATH, "LIBRARY_NAME":LIBRARY_NAME,
            "TOP_FOLDER":TOP_FOLDER, "FIELD_VALUE":FIELD_VALUE,
            "OPENAI_API_KEY":openai.api_key,
            "CHROMA_DIR":CHROMA_DIR, "MANIFEST_PATH":MANIFEST_PATH,
            "COLLECTION_NAME":COLLECTION_NAME
        }.items() if not v]
        logger.error(f"Missing environment variables: {missing}")
        raise RuntimeError(f"Missing environment variables: {missing}")
except Exception as e:
    logger.exception("Error during environment variable safety checks.")
    raise

logger.info(f"Using CHROMA_DIR = '{CHROMA_DIR}'")
logger.info(f"Using COLLECTION_NAME = '{COLLECTION_NAME}'")
logger.info(f"Using MANIFEST_PATH = '{MANIFEST_PATH}'\n")


# ─── Graph auth & helper functions ───────────────────────────────────────────────
def get_access_token() -> str:
    try:
        app = ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}"
        )
        token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in token:
            logger.error(f"Failed to obtain access token: {token}")
            raise RuntimeError(f"Failed to obtain access token: {token}")
        return token["access_token"]
    except Exception as e:
        logger.exception("Error obtaining access token.")
        raise

def get_site_id(token: str) -> str:
    try:
        url = f"https://graph.microsoft.com/v1.0/sites/{HOSTNAME}:{SITE_PATH}"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()["id"]
    except Exception as e:
        logger.exception("Error getting site ID.")
        raise

def get_drive_id(token: str, site_id: str) -> str:
    try:
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        for d in r.json().get("value", []):
            if d["name"] == LIBRARY_NAME:
                return d["id"]
        logger.error(f"Drive '{LIBRARY_NAME}' not found.")
        raise RuntimeError(f"Drive '{LIBRARY_NAME}' not found.")
    except Exception as e:
        logger.exception("Error getting drive ID.")
        raise

def list_children(token: str, drive_id: str, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        if parent_id:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{parent_id}/children"
        else:
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"
        items = []
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("value", []))
        while "@odata.nextLink" in data:
            r = requests.get(data["@odata.nextLink"], headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            data = r.json()
            items.extend(data.get("value", []))
        return items
    except Exception as e:
        logger.exception("Error listing children.")
        raise

def traverse_folder(token: str, drive_id: str, parent_id: str) -> List[Dict[str, Any]]:
    try:
        found = []
        for item in list_children(token, drive_id, parent_id):
            if "folder" in item:
                found.extend(traverse_folder(token, drive_id, item["id"]))
            elif "file" in item:
                found.append(item)
        return found
    except Exception as e:
        logger.exception("Error traversing folder.")
        raise

def get_drive_item(token: str, drive_id: str, item_id: str) -> Dict[str, Any]:
    try:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("Error getting drive item.")
        raise


# ─── Download & extract Word content ─────────────────────────────────────────────
def download_file(token: str, drive_id: str, item_id: str) -> bytes:
    try:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        return r.content
    except Exception as e:
        logger.exception(f"Error downloading file {item_id}.")
        raise

def extract_docx_text(file_bytes: bytes) -> str:
    try:
        doc = Document(BytesIO(file_bytes))
        # Join only non‐empty paragraphs
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        # Check for BadZipFile or similar errors and log a more helpful message
        import zipfile
        if isinstance(e, zipfile.BadZipFile):
            logger.error("File is not a valid .docx (zip) file. Skipping this file.")
            return ""  # Return empty string to skip further processing
        logger.exception("Error extracting text from DOCX.")
        return ""  # Return empty string to skip further processing


# ─── Chunk, embed, and upsert to Chroma ──────────────────────────────────────────
def chunk_text(text: str, max_tokens: int = 500, overlap: int = 50) -> List[str]:
    try:
        words = text.split()
        chunks, start = [], 0
        while start < len(words):
            end = start + max_tokens
            chunks.append(" ".join(words[start:end]))
            start = max(end - overlap, end)
        return chunks
    except Exception as e:
        logger.exception("Error chunking text.")
        raise

def embed_batches(texts: List[str], model: str = "text-embedding-ada-002") -> List[List[float]]:
    try:
        if not texts:
            return []
        resp = openai.Embedding.create(input=texts, model=model)
        return [d.embedding for d in resp["data"]]
    except Exception as e:
        logger.exception("Error embedding batches.")
        raise

def init_vector_store() -> PersistentClient:
    try:
        # Make sure CHROMA_DIR exists (create folder if needed)
        os.makedirs(CHROMA_DIR, exist_ok=True)
        client = PersistentClient(path=CHROMA_DIR)
        _ = client.get_or_create_collection(name=COLLECTION_NAME, metadata={"source": "sharepoint"})
        return client
    except Exception as e:
        logger.exception("Error initializing vector store.")
        raise


# ─── Main ingestion flow with manifest & cleanup ─────────────────────────────────
def run_ingestion(FIELD_VALUE, TOP_FOLDER):
    try:
        # 1) Load or initialize manifest
        if os.path.exists(MANIFEST_PATH):
            logger.info(f"Manifest file '{MANIFEST_PATH}' already exists. Loading contents:")
            with open(MANIFEST_PATH, "r") as f:
                manifest = json.load(f)
            for vid, info in manifest.items():
                logger.info(f"  • {vid} → last_modified = {info.get('last_modified')}, chunk_count = {info.get('chunk_count')}")
            logger.warning("Because the manifest exists, every file found below will be skipped unless its timestamp differs. If this is your first run and you expected ingestion, delete the manifest file and re-run.")
        else:
            logger.info(f"Manifest file '{MANIFEST_PATH}' not found. A new one will be created.")
            manifest = {}

        new_manifest: Dict[str, Dict[str, Any]] = {}
        all_current_ids = set()
        total_upserted = 0

        # 2) Authenticate & find site/drive
        token    = get_access_token()
        site_id  = get_site_id(token)
        drive_id = get_drive_id(token, site_id)

        # 3) Find TOP_FOLDER under the library
        # Replace 'Senso Y' with 'Senso-Y' for folder lookup
        lookup_top_folder = TOP_FOLDER
        if lookup_top_folder == "Senso Y":
            lookup_top_folder = "Senso-Y"
        root_items = list_children(token, drive_id)
        top = next((i for i in root_items if i["name"] == lookup_top_folder and "folder" in i), None)
        if not top:
            logger.error(f"Top-level folder '{lookup_top_folder}' not found in library '{LIBRARY_NAME}'. Skipping this ingestion run.")
            return  # Skip this post if not found

        # 4) Filter second-level subfolders by FIELD_VALUE
        second_items = list_children(token, drive_id, parent_id=top["id"])
        matched_folders = [
            f for f in second_items
            if "folder" in f and fnmatch.fnmatch(f["name"], f"*{FIELD_VALUE}*")
        ]

        if not matched_folders:
            logger.warning(f"No subfolders under '{TOP_FOLDER}' matched '*{FIELD_VALUE}*'. Exiting.")
            return

        # 5) Initialize Chroma and check initial count
        client     = init_vector_store()
        collection = client.get_or_create_collection(name=COLLECTION_NAME)
        try:
            initial_resp = collection.get(include=["documents", "metadatas", "embeddings"])
            initial_ids = initial_resp["ids"]
            logger.info(f"Chroma collection '{COLLECTION_NAME}' opened. Initial size: {len(initial_ids)} chunks.")
        except Exception as e:
            logger.warning(f"Could not fetch initial collection size: {e}")
            initial_ids = []

        # 6) Loop over matched folders and ingest
        for folder in matched_folders:
            logger.info(f"→ Processing folder: {folder['name']}")
            files_in_folder = traverse_folder(token, drive_id, folder["id"])
            if not files_in_folder:
                logger.info("  (No files found in this folder.)")
                continue

            for f in files_in_folder:
                fname = f["name"]
                if not fname.lower().endswith(".docx"):
                    logger.info(f"  Skipping non-docx file: {fname}")
                    continue

                # 6a) Fetch the file’s metadata (including lastModifiedDateTime)
                item = get_drive_item(token, drive_id, f["id"])
                lm   = item["lastModifiedDateTime"]
                new_manifest[f["id"]] = {"last_modified": lm}

                # 6b) Check manifest: skip if unchanged
                old = manifest.get(f["id"], {})
                if old.get("last_modified") == lm:
                    chunk_count = old.get("chunk_count", 0) or 0
                    if chunk_count:
                        logger.info(f"  → '{f['name']}' unchanged. Reserving {chunk_count} old chunk IDs.")
                    else:
                        logger.info(f"  → '{f['name']}' unchanged, but old chunk_count was None/0, so no IDs reserved.")
                    for i in range(chunk_count):
                        all_current_ids.add(f"{f['id']}_{i}")
                    continue

                # 6c) (Re)ingest this file because it’s new or modified
                logger.info(f"  ⇒ Ingesting '{fname}' (lastModified: {lm})")
                try:
                    data      = download_file(token, drive_id, f["id"])
                    text      = extract_docx_text(data)
                    chunks    = chunk_text(text)
                    embeddings = embed_batches(chunks)
                except Exception as e:
                    logger.error(f"    • Error processing '{fname}': {e}")
                    new_manifest[f["id"]]["chunk_count"] = 0
                    continue

                if not chunks:
                    logger.warning(f"    • No text extracted from '{fname}'. Skipping upsert.")
                    new_manifest[f["id"]]["chunk_count"] = 0
                    continue

                ids = [f"{f['id']}_{i}" for i in range(len(chunks))]
                all_current_ids.update(ids)
                new_manifest[f["id"]]["chunk_count"] = len(chunks)

                metadatas = [
                    {
                        "source":        f["webUrl"],
                        "file_name":     fname,
                        "folder":        folder["name"],
                        "name":         folder["name"],
                        "chunk_index":   i,
                        "last_modified": lm,
                    }
                    for i in range(len(chunks))
                ]

                # 6d) Upsert into Chroma
                try:
                    collection.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
                    logger.info(f"    • Upserted {len(chunks)} chunks for '{fname}'")
                    # Log the FIELD_VALUE (person's name) if successfully loaded
                    logger.info(f"Successfully loaded to ChromaDB: {FIELD_VALUE}")
                except Exception as e:
                    logger.error(f"    • Error upserting '{fname}': {e}")
                    continue

                total_upserted += len(chunks)

                # 6e) Immediately verify that the chunks were written
                try:
                    check_resp = collection.get(include=["documents", "metadatas", "embeddings"])
                    current_ids = check_resp["ids"]
                    logger.info(f"    → After upsert, collection size: {len(current_ids)} chunks")
                except Exception as e:
                    logger.warning(f"    → Could not verify collection size after upsert: {e}")

        # 7) Report how many were upserted
        logger.info(f"Total new chunks ingested this run: {total_upserted}")

        # 8) Cleanup: delete any vectors whose IDs aren’t in this run
        logger.info("—— Cleanup Phase —————————————————————————————————————————")
        try:
            before_resp = collection.get(include=["documents", "metadatas", "embeddings"])
            before_ids  = before_resp["ids"]
            logger.info(f"Existing IDs before cleanup: {len(before_ids)}")
        except Exception as e:
            logger.warning(f"Could not fetch existing IDs before cleanup: {e}")
            before_ids = []

        to_delete = [vid for vid in before_ids if vid not in all_current_ids]
        if to_delete:
            logger.info(f"  • Deleting {len(to_delete)} stale chunk IDs...")
            try:
                collection.delete(ids=to_delete)
            except Exception as e:
                logger.error(f"  • Error deleting stale IDs: {e}")
        else:
            logger.info("  • No stale IDs to delete.")

        try:
            after_resp = collection.get(include=["documents", "metadatas", "embeddings"])
            after_ids  = after_resp["ids"]
            logger.info(f"Collection size after cleanup: {len(after_ids)}")
        except Exception as e:
            logger.warning(f"Could not fetch collection size after cleanup: {e}")

        # 9) Persist the new manifest
        with open(MANIFEST_PATH, "w") as f:
            json.dump(new_manifest, f, indent=2)
        logger.info("Manifest written. Next run will skip unchanged files.")

        # 10) Cleanly shut down Chroma’s background threads:
        try:
            client.shutdown()
            logger.info("Chroma client shutdown complete.")
        except AttributeError:
            pass

        logger.info("Ingestion run complete.")
    except Exception as e:
        logger.exception("Fatal error in run_ingestion.")
        raise

# Provide a public function for external calls

# def ingest_sharepoint_cv():
#     run_ingestion()

if __name__ == "__main__":
    run_ingestion(FIELD_VALUE=FIELD_VALUE, TOP_FOLDER=TOP_FOLDER)
