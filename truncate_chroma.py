#!/usr/bin/env python3
import os
import sys
import argparse
import shutil
import time
from chromadb import PersistentClient

def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val

def confirm_or_exit(question: str, assume_yes: bool):
    if assume_yes:
        return
    ans = input(f"{question} [y/N]: ").strip().lower()
    if ans not in ("y", "yes"):
        print("Aborted.")
        sys.exit(1)

def backup_dir(path: str) -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    archive_base = f"{os.path.basename(path.rstrip(os.sep))}-backup-{ts}"
    parent = os.path.dirname(os.path.abspath(path))
    archive_path = shutil.make_archive(
        base_name=os.path.join(parent, archive_base),
        format="zip",
        root_dir=parent,
        base_dir=os.path.basename(path.rstrip(os.sep)),
    )
    return archive_path

def delete_collection(chroma_dir: str, collection_name: str):
    client = PersistentClient(path=chroma_dir)
    # If collection doesn't exist, delete_collection will raise; we’ll handle gracefully
    try:
        client.delete_collection(name=collection_name)
        print(f"Deleted collection '{collection_name}' in '{chroma_dir}'.")
    except Exception as e:
        # Try to detect if it simply doesn't exist
        try:
            _ = client.get_collection(collection_name)
            # If this succeeds, re-raise original error
            raise
        except Exception:
            print(f"Collection '{collection_name}' not found. Nothing to delete.")
    finally:
        try:
            client.shutdown()
        except AttributeError:
            pass

def remove_manifest(manifest_path: str):
    try:
        if manifest_path and os.path.exists(manifest_path):
            os.remove(manifest_path)
            print(f"Removed manifest: {manifest_path}")
        else:
            print("Manifest not found; nothing to remove.")
    except Exception as e:
        print(f"Warning: failed to remove manifest '{manifest_path}': {e}")

def wipe_chroma_dir(chroma_dir: str, do_backup: bool):
    if not os.path.exists(chroma_dir):
        print(f"CHROMA_DIR '{chroma_dir}' does not exist; nothing to wipe.")
        return
    if do_backup:
        try:
            archive = backup_dir(chroma_dir)
            print(f"Backup created: {archive}")
        except Exception as e:
            print(f"Warning: backup failed: {e}")
    shutil.rmtree(chroma_dir, ignore_errors=False)
    print(f"Wiped CHROMA_DIR: {chroma_dir}")

def main():
    parser = argparse.ArgumentParser(
        description="Truncate Chroma DB: delete a collection or wipe the entire CHROMA_DIR."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--all",
        action="store_true",
        help="Wipe the entire CHROMA_DIR directory on disk (stronger than deleting a single collection).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompts.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a zip backup of CHROMA_DIR before wiping (only used with --all).",
    )
    parser.add_argument(
        "--wipe-manifest",
        action="store_true",
        help="Remove MANIFEST_PATH file as well.",
    )
    args = parser.parse_args()

    chroma_dir = require_env("CHROMA_DIR")
    collection_name = os.getenv("COLLECTION_NAME")  # only needed for collection delete
    manifest_path = os.getenv("MANIFEST_PATH", "")

    if args.all:
        confirm_or_exit(
            f"About to WIPE the entire CHROMA_DIR at '{chroma_dir}'. Continue?",
            args.yes,
        )
        wipe_chroma_dir(chroma_dir, do_backup=args.backup)
    else:
        if not collection_name:
            raise RuntimeError("COLLECTION_NAME must be set to delete a collection.")
        confirm_or_exit(
            f"About to DELETE collection '{collection_name}' in '{chroma_dir}'. Continue?",
            args.yes,
        )
        delete_collection(chroma_dir, collection_name)

    if args.wipe_manifest and manifest_path:
        confirm_or_exit(
            f"Also remove manifest file at '{manifest_path}'?",
            args.yes,
        )
        remove_manifest(manifest_path)

    print("Done.")

if __name__ == "__main__":
    main()
