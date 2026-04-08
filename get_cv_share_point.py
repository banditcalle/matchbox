import json
import logging
import os
from io import BytesIO
from typing import Any, Dict, List, Optional

import fnmatch
import requests
from chromadb import PersistentClient
from docx import Document
from dotenv import load_dotenv
from msal import ConfidentialClientApplication
from openai import OpenAI


load_dotenv()

LOG_FILE = os.getenv("LOG_FILE", os.path.join("logs", "get_cv_sharepoint.log"))
ERROR_LOG_FILE = os.getenv("ERROR_LOG_FILE", os.path.join("logs", "get_cv_share_point_errors.log"))


def configure_logging() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError as e:
        root_logger.warning(f"Could not open log file '{LOG_FILE}': {e}. Continuing with console logging only.")

    try:
        error_handler = logging.FileHandler(ERROR_LOG_FILE, mode="a", encoding="utf-8")
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)
    except OSError as e:
        root_logger.warning(f"Could not open error log file '{ERROR_LOG_FILE}': {e}.")

    return logging.getLogger(__name__)


logger = configure_logging()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

HOSTNAME = os.getenv("HOSTNAME")
SITE_PATH = os.getenv("SITE_PATH")
LIBRARY_NAME = os.getenv("LIBRARY_NAME")
TOP_FOLDER = os.getenv("TOP_FOLDER")
FIELD_VALUE = os.getenv("FIELD_VALUE")

ONLY_ONE_CV_PER_FIELD_VALUE = os.getenv("ONLY_ONE_CV_PER_FIELD_VALUE", "0").lower() in ("1", "true", "yes")
INGEST_ALL_DOCX = os.getenv("INGEST_ALL_DOCX", "0").lower() in ("1", "true", "yes")
ENABLE_CLEANUP = os.getenv("ENABLE_CLEANUP", "0").lower() in ("1", "true", "yes")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHROMA_DIR = os.getenv("CHROMA_DIR")
MANIFEST_PATH = os.getenv("MANIFEST_PATH")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")


def validate_environment() -> None:
    required = {
        "TENANT_ID": TENANT_ID,
        "CLIENT_ID": CLIENT_ID,
        "CLIENT_SECRET": CLIENT_SECRET,
        "HOSTNAME": HOSTNAME,
        "SITE_PATH": SITE_PATH,
        "LIBRARY_NAME": LIBRARY_NAME,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "CHROMA_DIR": CHROMA_DIR,
        "MANIFEST_PATH": MANIFEST_PATH,
        "COLLECTION_NAME": COLLECTION_NAME,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        logger.error(f"Missing environment variables: {missing}")
        raise RuntimeError(f"Missing environment variables: {missing}")

    if not INGEST_ALL_DOCX:
        targeted_required = {"TOP_FOLDER": TOP_FOLDER, "FIELD_VALUE": FIELD_VALUE}
        targeted_missing = [key for key, value in targeted_required.items() if not value]
        if targeted_missing:
            logger.error(f"Missing environment variables for targeted ingestion: {targeted_missing}")
            raise RuntimeError(f"Missing environment variables for targeted ingestion: {targeted_missing}")


validate_environment()

logger.info(f"Using CHROMA_DIR = '{CHROMA_DIR}'")
logger.info(f"Using COLLECTION_NAME = '{COLLECTION_NAME}'")
logger.info(f"Using MANIFEST_PATH = '{MANIFEST_PATH}'")
logger.info(f"INGEST_ALL_DOCX = {INGEST_ALL_DOCX}")

openai_client = OpenAI(api_key=OPENAI_API_KEY)


def get_access_token() -> str:
    app = ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )
    token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in token:
        logger.error(f"Failed to obtain access token: {token}")
        raise RuntimeError(f"Failed to obtain access token: {token}")
    return token["access_token"]


def get_site_id(token: str) -> str:
    url = f"https://graph.microsoft.com/v1.0/sites/{HOSTNAME}:{SITE_PATH}"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    return response.json()["id"]


def get_drive_id(token: str, site_id: str) -> str:
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    for drive in response.json().get("value", []):
        if drive["name"] == LIBRARY_NAME:
            return drive["id"]
    raise RuntimeError(f"Drive '{LIBRARY_NAME}' not found.")


def list_children(token: str, drive_id: str, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if parent_id:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{parent_id}/children"
    else:
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"

    items: List[Dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    items.extend(data.get("value", []))

    while "@odata.nextLink" in data:
        response = requests.get(data["@odata.nextLink"], headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        items.extend(data.get("value", []))

    return items


def traverse_folder(token: str, drive_id: str, parent_id: str) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for item in list_children(token, drive_id, parent_id):
        if "folder" in item:
            found.extend(traverse_folder(token, drive_id, item["id"]))
        elif "file" in item:
            found.append(item)
    return found


def get_drive_item(token: str, drive_id: str, item_id: str) -> Dict[str, Any]:
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    return response.json()


def download_file(token: str, drive_id: str, item_id: str) -> bytes:
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    response.raise_for_status()
    return response.content


def extract_docx_text(file_bytes: bytes) -> str:
    try:
        doc = Document(BytesIO(file_bytes))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())
    except Exception as e:
        import zipfile

        if isinstance(e, zipfile.BadZipFile):
            logger.error("File is not a valid .docx (zip) file. Skipping this file.")
            return ""
        logger.exception("Error extracting text from DOCX.")
        return ""


def chunk_text(text: str, max_tokens: int = 500, overlap: int = 50) -> List[str]:
    words = text.split()
    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = start + max_tokens
        chunks.append(" ".join(words[start:end]))
        start = max(end - overlap, end)
    return chunks


def embed_batches(texts: List[str], model: str = EMBEDDING_MODEL) -> List[List[float]]:
    if not texts:
        return []
    response = openai_client.embeddings.create(input=texts, model=model)
    return [item.embedding for item in response.data]


def init_vector_store() -> PersistentClient:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    client = PersistentClient(path=CHROMA_DIR)
    client.get_or_create_collection(name=COLLECTION_NAME, metadata={"source": "sharepoint"})
    return client


def load_manifest() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(MANIFEST_PATH):
        logger.info(f"Manifest file '{MANIFEST_PATH}' not found. A new one will be created.")
        return {}

    logger.info(f"Manifest file '{MANIFEST_PATH}' already exists. Loading contents.")
    with open(MANIFEST_PATH, "r", encoding="utf-8") as file_handle:
        manifest = json.load(file_handle)
    logger.warning("Because the manifest exists, unchanged files will be skipped. Delete the manifest to force a full reingestion.")
    return manifest


def write_manifest(manifest: Dict[str, Dict[str, Any]]) -> None:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as file_handle:
        json.dump(manifest, file_handle, indent=2)
    logger.info("Manifest written. Next run will skip unchanged files.")


def normalize_top_folder_name(folder_name: str) -> str:
    return "Senso-Y" if folder_name == "Senso Y" else folder_name


def get_target_folders(token: str, drive_id: str, top_folder_name: str, field_value: str) -> List[Dict[str, Any]]:
    lookup_top_folder = normalize_top_folder_name(top_folder_name)
    root_items = list_children(token, drive_id)
    top = next((item for item in root_items if item["name"] == lookup_top_folder and "folder" in item), None)
    if not top:
        logger.error(f"Top-level folder '{lookup_top_folder}' not found in library '{LIBRARY_NAME}'.")
        return []

    second_level_items = list_children(token, drive_id, parent_id=top["id"])
    matched_folders = [
        item for item in second_level_items if "folder" in item and fnmatch.fnmatch(item["name"], f"*{field_value}*")
    ]
    if not matched_folders:
        logger.warning(f"No subfolders under '{top_folder_name}' matched '*{field_value}*'.")
        return []

    if ONLY_ONE_CV_PER_FIELD_VALUE:
        logger.info("ONLY_ONE_CV_PER_FIELD_VALUE is set: only the first matching folder will be processed.")
        return matched_folders[:1]
    return matched_folders


def get_all_top_level_folders(token: str, drive_id: str) -> List[Dict[str, Any]]:
    return [item for item in list_children(token, drive_id) if "folder" in item]


def cleanup_deleted_files(collection: Any, current_base_file_ids: set[str]) -> None:
    if not ENABLE_CLEANUP:
        logger.info("Cleanup disabled (ENABLE_CLEANUP=0). Skipping deletion of any existing vectors.")
        return

    try:
        before_response = collection.get(include=["metadatas"])
        before_ids = before_response["ids"]
        logger.info(f"Existing IDs before cleanup: {len(before_ids)}")

        def base_of(vector_id: str) -> str:
            if "::" in vector_id:
                return vector_id.split("::", 1)[0]
            return vector_id.split("_", 1)[0]

        to_delete = [vector_id for vector_id in before_ids if base_of(vector_id) not in current_base_file_ids]
        if to_delete:
            logger.info(f"Deleting {len(to_delete)} stale chunk IDs for files no longer present.")
            collection.delete(ids=to_delete)
        else:
            logger.info("No stale IDs to delete.")
    except Exception as e:
        logger.warning(f"Cleanup skipped due to error reading collection: {e}")


def ingest_folders(
    token: str,
    drive_id: str,
    folders: List[Dict[str, Any]],
    manifest: Dict[str, Dict[str, Any]],
    run_label: str,
) -> None:
    new_manifest: Dict[str, Dict[str, Any]] = {}
    total_upserted = 0
    current_base_file_ids: set[str] = set()

    client = init_vector_store()
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    try:
        logger.info(f"Chroma collection '{COLLECTION_NAME}' opened. Initial size: {collection.count()} chunks.")
    except Exception as e:
        logger.warning(f"Could not fetch initial collection size: {e}")

    try:
        for folder in folders:
            logger.info(f"Processing folder: {folder['name']}")
            files_in_folder = traverse_folder(token, drive_id, folder["id"])
            if not files_in_folder:
                logger.info("  No files found in this folder.")
                continue

            files_to_process = files_in_folder
            if ONLY_ONE_CV_PER_FIELD_VALUE and not INGEST_ALL_DOCX:
                docx_files = [item for item in files_in_folder if item["name"].lower().endswith(".docx")]
                files_to_process = [docx_files[0]] if docx_files else []

            for file_item in files_to_process:
                file_name = file_item["name"]
                if not file_name.lower().endswith(".docx"):
                    logger.info(f"  Skipping non-docx file: {file_name}")
                    continue

                item_metadata = get_drive_item(token, drive_id, file_item["id"])
                last_modified = item_metadata["lastModifiedDateTime"]
                new_manifest[file_item["id"]] = {"last_modified": last_modified}
                current_base_file_ids.add(file_item["id"])

                old = manifest.get(file_item["id"], {})
                if old.get("last_modified") == last_modified:
                    chunk_count = old.get("chunk_count", 0) or 0
                    logger.info(f"  '{file_name}' unchanged. Keeping previous chunk count: {chunk_count}")
                    new_manifest[file_item["id"]]["chunk_count"] = chunk_count
                    continue

                logger.info(f"  Ingesting '{file_name}' (lastModified: {last_modified})")
                try:
                    data = download_file(token, drive_id, file_item["id"])
                    text = extract_docx_text(data)
                    chunks = chunk_text(text)
                    embeddings = embed_batches(chunks)
                except Exception as e:
                    logger.error(f"  Error processing '{file_name}': {e}")
                    new_manifest[file_item["id"]]["chunk_count"] = 0
                    continue

                if not chunks:
                    logger.warning(f"  No text extracted from '{file_name}'. Skipping upsert.")
                    new_manifest[file_item["id"]]["chunk_count"] = 0
                    continue

                ids = [f"{file_item['id']}::{last_modified}::{index}" for index in range(len(chunks))]
                metadatas = [
                    {
                        "source": file_item["webUrl"],
                        "file_name": file_name,
                        "folder": folder["name"],
                        "name": folder["name"],
                        "chunk_index": index,
                        "last_modified": last_modified,
                    }
                    for index in range(len(chunks))
                ]

                try:
                    collection.upsert(ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings)
                    logger.info(f"  Upserted {len(chunks)} chunks for '{file_name}'")
                    logger.info(f"Successfully loaded to ChromaDB: {run_label}")
                    total_upserted += len(chunks)
                    new_manifest[file_item["id"]]["chunk_count"] = len(chunks)
                except Exception as e:
                    logger.error(f"  Error upserting '{file_name}': {e}")
                    new_manifest[file_item["id"]]["chunk_count"] = 0

        logger.info(f"Total new chunks ingested this run: {total_upserted}")
        cleanup_deleted_files(collection, current_base_file_ids)
        merged_manifest = manifest.copy()
        merged_manifest.update(new_manifest)
        write_manifest(merged_manifest)
    finally:
        try:
            client.shutdown()
            logger.info("Chroma client shutdown complete.")
        except AttributeError:
            pass

    logger.info("Ingestion run complete.")


def run_ingestion(FIELD_VALUE: str, TOP_FOLDER: str) -> None:
    try:
        manifest = load_manifest()
        token = get_access_token()
        site_id = get_site_id(token)
        drive_id = get_drive_id(token, site_id)
        folders = get_target_folders(token, drive_id, TOP_FOLDER, FIELD_VALUE)
        if not folders:
            return
        ingest_folders(token, drive_id, folders, manifest, run_label=FIELD_VALUE)
    except Exception:
        logger.exception("Fatal error in run_ingestion.")
        raise


def run_full_ingestion() -> None:
    try:
        manifest = load_manifest()
        token = get_access_token()
        site_id = get_site_id(token)
        drive_id = get_drive_id(token, site_id)
        folders = get_all_top_level_folders(token, drive_id)
        if not folders:
            logger.warning(f"No top-level folders found in library '{LIBRARY_NAME}'.")
            return
        ingest_folders(token, drive_id, folders, manifest, run_label="ALL_DOCX")
    except Exception:
        logger.exception("Fatal error in run_full_ingestion.")
        raise


if __name__ == "__main__":
    if INGEST_ALL_DOCX:
        run_full_ingestion()
    else:
        run_ingestion(FIELD_VALUE=FIELD_VALUE, TOP_FOLDER=TOP_FOLDER)
