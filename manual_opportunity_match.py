import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from chromadb import PersistentClient
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

CHROMA_DIR = os.getenv("CHROMA_DIR")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "75"))
# Important: query embeddings must use the same model family as the vectors
# already stored in ChromaDB. The current SharePoint ingestion defaults to
# text-embedding-ada-002 unless EMBEDDING_MODEL is explicitly set.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")


def require_env(name: str, value: str | None) -> str:
    """Fail fast when a required environment variable is missing."""
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_args() -> argparse.Namespace:
    """Define CLI options for loading an opportunity and tuning shortlist output."""
    parser = argparse.ArgumentParser(
        description="Match an opportunity text against the local ChromaDB and return shortlist candidates."
    )
    parser.add_argument("--text", help="Opportunity text to match.")
    parser.add_argument("--file", help="Path to a text file containing the opportunity text.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=MATCH_THRESHOLD,
        help="Minimum match rate percentage to keep in the result list.",
    )
    parser.add_argument(
        "--top-k-chunks",
        type=int,
        default=150,
        help="How many top chunk hits to pull back from Chroma before grouping into candidates.",
    )
    parser.add_argument(
        "--top-candidates",
        type=int,
        default=25,
        help="Maximum number of grouped candidates to print.",
    )
    parser.add_argument(
        "--json-out",
        help="Optional path to save the shortlist as JSON for later OpenAI analysis.",
    )
    return parser.parse_args()


def read_opportunity_text(args: argparse.Namespace) -> str:
    """Get opportunity text from --text, --file, or interactive stdin input."""
    if args.text:
        return args.text.strip()

    if args.file:
        return Path(args.file).read_text(encoding="utf-8").strip()

    print("Paste the opportunity text below.")
    print("Finish by typing END on its own line, or press Ctrl+Z and Enter on Windows.")
    lines: List[str] = []
    try:
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
    except EOFError:
        pass

    text = "\n".join(lines).strip()
    if not text:
        raise RuntimeError("No opportunity text provided.")
    return text


def embed_text(client: OpenAI, text: str) -> List[float]:
    """Create an embedding vector for the opportunity text."""
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def similarity_to_percent(distance: float) -> float:
    # Chroma often returns L2-style distances here, where lower is better and
    # the raw value is not directly a percentage. This keeps the score bounded
    # and monotonic so MATCH_THRESHOLD remains usable for shortlist filtering.
    return round((1 / (1 + max(distance, 0))) * 100, 1)


def guess_full_name(file_name: str) -> str:
    """Heuristically infer a person's name from a CV file name."""
    stem = Path(file_name).stem
    cleaned = stem
    cleaned = re.sub(r"(?i)\b(cv|resume|resum[eé]|konsultprofil|profil|avega group|avega)\b", " ", cleaned)
    cleaned = re.sub(r"[_\-–]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_")

    tokens = cleaned.split()
    capitalized = [token for token in tokens if token and token[0].isalpha() and token[0].isupper()]

    stopwords = {
        "sv", "sve", "swe", "eng", "english", "swedish", "ny", "version",
        "bild", "vanster", "vänster", "höger", "hoger", "copilottest",
        "förvaltningsledare", "forvaltningsledare", "sl", "swedbank",
        "consultant", "profile", "consultantprofile", "old", "new",
        "ikea", "seb", "shb", "hm", "ba", "etl", "de", "da", "bi",
        "exergi", "postnordba", "bankgirot", "nordea", "stewardship",
    }

    person_tokens: List[str] = []
    for token in capitalized:
        lowered = token.casefold()
        if lowered in stopwords:
            if len(person_tokens) >= 2:
                break
            continue
        if token.isdigit():
            break
        person_tokens.append(token)
        if len(person_tokens) == 3:
            break

    if len(person_tokens) >= 2:
        return " ".join(person_tokens[:2])

    lower_tokens = [token for token in tokens if token and token[0].isalpha()]
    if len(lower_tokens) >= 2:
        return " ".join(lower_tokens[:2]).title()

    return cleaned or stem


def normalize_person_key(full_name: str) -> str:
    """Normalize names to a stable grouping key across file naming variations."""
    normalized = full_name.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(
        r"\b(eng\d*|english|sv|swe|swedish|cv|resume|consultant|profile|avega|group)\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or full_name.casefold()


def group_candidate_matches(results: Dict[str, Any], threshold: float) -> List[Dict[str, Any]]:
    """Aggregate chunk-level Chroma hits into one entry per candidate."""
    grouped: Dict[str, Dict[str, Any]] = {}

    # Pair each metadata row with its distance score from the top query result set.
    for metadata, distance in zip(results["metadatas"][0], results["distances"][0]):
        if not metadata:
            continue

        match_rate = similarity_to_percent(distance)
        if match_rate < threshold:
            continue

        file_name = metadata.get("file_name", "Unknown file")
        source = metadata.get("source", "")
        company = metadata.get("folder") or metadata.get("name") or "Unknown company"
        full_name = guess_full_name(file_name)
        candidate_key = normalize_person_key(full_name)

        # Initialize a grouped candidate entry the first time we see this person.
        entry = grouped.get(candidate_key)
        if not entry:
            entry = {
                "company": company,
                "full_name": full_name,
                "match_rate": match_rate,
                "file_name": file_name,
                "source": source,
                "matched_chunks": 0,
                "sources": [],
                "file_names": [],
            }
            grouped[candidate_key] = entry

        entry["matched_chunks"] += 1
        # Keep the strongest single hit as the representative score/source.
        if match_rate > entry["match_rate"]:
            entry["match_rate"] = match_rate
            entry["file_name"] = file_name
            entry["source"] = source
            entry["company"] = company

        if source and source not in entry["sources"]:
            entry["sources"].append(source)
        if file_name not in entry["file_names"]:
            entry["file_names"].append(file_name)

    candidates = list(grouped.values())
    candidates.sort(key=lambda item: (-item["match_rate"], -item["matched_chunks"], item["full_name"]))
    return candidates


def print_candidates(candidates: List[Dict[str, Any]]) -> None:
    """Print shortlisted candidates in a compact human-readable format."""
    if not candidates:
        print("No candidates met the match threshold.")
        return

    print("\nCandidates above threshold:\n")
    for index, candidate in enumerate(candidates, start=1):
        print(
            f"{index}. {candidate['full_name']} | {candidate['company']} | "
            f"{candidate['match_rate']}% | chunks: {candidate['matched_chunks']}"
        )
        print(f"   file: {candidate['file_name']}")
        if candidate["source"]:
            print(f"   source: {candidate['source']}")


def main() -> None:
    """Run the end-to-end manual matching flow from input to shortlist output."""
    args = parse_args()
    opportunity_text = read_opportunity_text(args)

    chroma_dir = require_env("CHROMA_DIR", CHROMA_DIR)
    collection_name = require_env("COLLECTION_NAME", COLLECTION_NAME)
    api_key = require_env("OPENAI_API_KEY", OPENAI_API_KEY)

    openai_client = OpenAI(api_key=api_key)
    # Build a query embedding using the same embedding family as ingested vectors.
    query_embedding = embed_text(openai_client, opportunity_text)

    chroma_client = PersistentClient(path=chroma_dir)
    collection = chroma_client.get_collection(name=collection_name)
    # Retrieve top chunk-level matches, then group them into person-level candidates.
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=args.top_k_chunks,
        include=["metadatas", "distances"],
    )

    candidates = group_candidate_matches(results, threshold=args.threshold)
    shortlist = candidates[: args.top_candidates]

    print_candidates(shortlist)

    if args.json_out:
        # Optional machine-readable output for downstream analysis workflows.
        output_path = Path(args.json_out)
        output_path.write_text(json.dumps(shortlist, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved shortlist JSON to {output_path}")


if __name__ == "__main__":
    main()
