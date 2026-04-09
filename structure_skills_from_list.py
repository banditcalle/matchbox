import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from chromadb import PersistentClient
from dotenv import load_dotenv


load_dotenv()


DURATION_PATTERNS = [
    re.compile(r"(?P<value>\d+)\s*\+?\s*(?P<unit>years?|yrs?)", re.IGNORECASE),
    re.compile(r"(?P<value>\d+)\s*\+?\s*(?P<unit>months?|mos?)", re.IGNORECASE),
    re.compile(r"since\s+(?P<year>20\d{2}|19\d{2})", re.IGNORECASE),
]


@dataclass
class KnowledgeArea:
    area: str
    vendor: str
    aliases: List[str]


@dataclass
class Certification:
    certification_name: str
    vendor: str
    area: str
    level: str
    aliases: List[str]


def _split_aliases(value: str) -> List[str]:
    return [a.strip().lower() for a in (value or "").split("|") if a.strip()]


def _normalize_for_match(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def load_knowledge_areas(path: str) -> List[KnowledgeArea]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            KnowledgeArea(
                area=row["area"].strip(),
                vendor=row["vendor"].strip(),
                aliases=_split_aliases(row.get("aliases", "")),
            )
            for row in reader
        ]


def load_certifications(path: str) -> List[Certification]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            Certification(
                certification_name=row["certification_name"].strip(),
                vendor=row["vendor"].strip(),
                area=row["area"].strip(),
                level=row.get("level", "").strip(),
                aliases=_split_aliases(row.get("aliases", "")),
            )
            for row in reader
        ]


def _find_sentences_with_aliases(text: str, aliases: List[str]) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    found = []
    normalized_aliases = [_normalize_for_match(alias) for alias in aliases if alias.strip()]
    for sentence in sentences:
        s = _normalize_for_match(sentence)
        if any(alias and alias in s for alias in normalized_aliases):
            found.append(sentence.strip())
    return found


def _duration_from_sentence(sentence: str, now_year: int) -> int:
    months = 0
    for pattern in DURATION_PATTERNS:
        match = pattern.search(sentence)
        if not match:
            continue

        if "year" in match.groupdict():
            start_year = int(match.group("year"))
            months = max(months, (now_year - start_year) * 12)
            continue

        value = int(match.group("value"))
        unit = match.group("unit").lower()
        if unit.startswith("year") or unit.startswith("yr"):
            months = max(months, value * 12)
        else:
            months = max(months, value)
    return months


def extract_profile_signals(
    profile_id: str,
    text: str,
    knowledge_areas: List[KnowledgeArea],
    certifications: List[Certification],
    now_year: int,
    metadata: Dict | None = None,
) -> Dict:
    normalized_text = _normalize_for_match(text)

    cert_hits = []
    seen_certifications = set()
    for cert in certifications:
        terms = [_normalize_for_match(cert.certification_name)] + [
            _normalize_for_match(alias) for alias in cert.aliases
        ]
        if any(term and term in normalized_text for term in terms):
            key = cert.certification_name.casefold()
            if key not in seen_certifications:
                cert_hits.append(
                    {
                        "certification_name": cert.certification_name,
                        "vendor": cert.vendor,
                        "area": cert.area,
                        "level": cert.level,
                    }
                )
                seen_certifications.add(key)

    area_records = []
    for area in knowledge_areas:
        if not area.aliases:
            continue

        matched_sentences = _find_sentences_with_aliases(text, area.aliases)
        if not matched_sentences:
            continue

        knowledge_months = 0
        for sentence in matched_sentences:
            knowledge_months = max(
                knowledge_months,
                _duration_from_sentence(sentence, now_year=now_year),
            )

        cert_names = [c["certification_name"] for c in cert_hits if c["area"] == area.area]

        area_records.append(
            {
                "area": area.area,
                "vendor": area.vendor,
                "knowledge_detected": True,
                "knowledge_months": knowledge_months,
                "cert_count": len(cert_names),
                "cert_names": cert_names,
                "knowledge_evidence": matched_sentences[:5],
            }
        )

    return {
        "profile_id": profile_id,
        **(metadata or {}),
        "areas": area_records,
        "certifications": cert_hits,
    }


def summarize(signals: List[Dict], certifications: List[Certification] | None = None) -> Dict:
    by_area: Dict[str, Dict] = {}
    by_certification: Dict[str, Dict] = {}

    for cert in certifications or []:
        cert_key = cert.certification_name.casefold()
        by_certification.setdefault(
            cert_key,
            {
                "certification_name": cert.certification_name,
                "vendor": cert.vendor,
                "area": cert.area,
                "level": cert.level,
                "profiles_with_certification": 0,
                "hits_total": 0,
            },
        )

    for profile in signals:
        for area in profile.get("areas", []):
            key = area["area"]
            rec = by_area.setdefault(
                key,
                {
                    "area": area["area"],
                    "vendor": area["vendor"],
                    "profiles_with_knowledge": 0,
                    "profiles_with_certifications": 0,
                    "certifications_total": 0,
                    "max_knowledge_months": 0,
                },
            )
            rec["profiles_with_knowledge"] += 1
            if area["cert_count"] > 0:
                rec["profiles_with_certifications"] += 1
            rec["certifications_total"] += area["cert_count"]
            rec["max_knowledge_months"] = max(rec["max_knowledge_months"], area["knowledge_months"])

        seen_in_profile = set()
        for cert in profile.get("certifications", []):
            cert_name = cert["certification_name"]
            cert_key = cert_name.casefold()
            rec = by_certification.setdefault(
                cert_key,
                {
                    "certification_name": cert_name,
                    "vendor": cert.get("vendor", ""),
                    "area": cert.get("area", ""),
                    "level": cert.get("level", ""),
                    "profiles_with_certification": 0,
                    "hits_total": 0,
                },
            )
            rec["hits_total"] += 1
            if cert_key not in seen_in_profile:
                rec["profiles_with_certification"] += 1
                seen_in_profile.add(cert_key)

    return {
        "area_summary": sorted(by_area.values(), key=lambda x: x["area"]),
        "certification_summary": sorted(
            by_certification.values(),
            key=lambda x: (-x["profiles_with_certification"], x["certification_name"]),
        ),
        "profile_count": len(signals),
    }


def load_profiles_from_dir(directory: str) -> List[Tuple[str, str]]:
    profiles = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".txt"):
            continue
        path = os.path.join(directory, filename)
        with open(path, "r", encoding="utf-8") as f:
            profiles.append((filename, f.read()))
    return profiles


def guess_full_name(file_name: str) -> str:
    stem = os.path.splitext(os.path.basename(file_name))[0]
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
    normalized = full_name.casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(
        r"\b(eng\d*|english|sv|swe|swedish|cv|resume|consultant|profile|avega|group)\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or full_name.casefold()


def load_profiles_from_chroma(chroma_dir: str, collection_name: str) -> List[Tuple[str, str, Dict]]:
    client = PersistentClient(path=chroma_dir)
    collection = client.get_collection(name=collection_name)
    response = collection.get(include=["documents", "metadatas"])

    grouped: Dict[str, Dict] = {}
    ids = response.get("ids", [])
    documents = response.get("documents", [])
    metadatas = response.get("metadatas", [])

    for vector_id, document, metadata in zip(ids, documents, metadatas):
        metadata = metadata or {}
        file_name = metadata.get("file_name") or metadata.get("source") or vector_id
        entry = grouped.setdefault(
            file_name,
            {
                "profile_id": file_name,
                "chunks": [],
                "metadata": {
                    "company": metadata.get("folder") or metadata.get("name") or "",
                    "source": metadata.get("source", ""),
                    "file_name": file_name,
                },
            },
        )
        if document:
            entry["chunks"].append(document)

    profiles: List[Tuple[str, str, Dict]] = []
    for file_name in sorted(grouped.keys()):
        entry = grouped[file_name]
        combined_text = "\n".join(entry["chunks"]).strip()
        profiles.append((entry["profile_id"], combined_text, entry["metadata"]))

    return profiles


def group_profiles_by_person(profiles: List[Tuple[str, str, Dict]]) -> List[Tuple[str, str, Dict]]:
    grouped: Dict[str, Dict] = {}

    for profile_id, text, metadata in profiles:
        file_name = metadata.get("file_name", profile_id)
        full_name = guess_full_name(file_name)
        person_key = normalize_person_key(full_name)

        entry = grouped.setdefault(
            person_key,
            {
                "profile_id": full_name,
                "texts": [],
                "companies": set(),
                "sources": set(),
                "file_names": set(),
                "metadata": {
                    "person_name": full_name,
                },
            },
        )

        if text:
            entry["texts"].append(text)
        if metadata.get("company"):
            entry["companies"].add(metadata["company"])
        if metadata.get("source"):
            entry["sources"].add(metadata["source"])
        if file_name:
            entry["file_names"].add(file_name)

    people: List[Tuple[str, str, Dict]] = []
    for person_key in sorted(grouped.keys()):
        entry = grouped[person_key]
        metadata = dict(entry["metadata"])
        metadata["company"] = sorted(entry["companies"])[0] if entry["companies"] else ""
        metadata["companies"] = sorted(entry["companies"])
        metadata["source"] = sorted(entry["sources"])[0] if entry["sources"] else ""
        metadata["sources"] = sorted(entry["sources"])
        metadata["file_name"] = sorted(entry["file_names"])[0] if entry["file_names"] else entry["profile_id"]
        metadata["file_names"] = sorted(entry["file_names"])
        metadata["cv_count"] = len(entry["file_names"])
        combined_text = "\n".join(entry["texts"]).strip()
        people.append((entry["profile_id"], combined_text, metadata))

    return people


def _slugify_area(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def parse_list_file(path: str) -> Tuple[List[str], List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f]

    mode = None
    knowledge_areas: List[str] = []
    certifications: List[str] = []

    for line in lines:
        if not line:
            continue

        lower = line.lower()
        if lower.startswith("# knowledge areas"):
            mode = "knowledge"
            continue
        if lower.startswith("# certifications"):
            mode = "certifications"
            continue
        if line.startswith("#"):
            continue

        entries = [item.strip() for item in line.split(",") if item.strip()]
        if mode == "knowledge":
            knowledge_areas.extend(entries)
        elif mode == "certifications":
            certifications.extend(entries)

    return knowledge_areas, certifications


def write_knowledge_areas_csv(path: str, areas: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["area", "vendor", "aliases"])
        writer.writeheader()
        for area in areas:
            writer.writerow(
                {
                    "area": area,
                    "vendor": "",
                    "aliases": _slugify_area(area),
                }
            )


def write_certifications_csv(path: str, certifications: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["certification_name", "vendor", "area", "level", "aliases"],
        )
        writer.writeheader()
        for certification in certifications:
            writer.writerow(
                {
                    "certification_name": certification,
                    "vendor": "",
                    "area": "",
                    "level": "",
                    "aliases": _slugify_area(certification),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create starter taxonomy CSVs from a list file or structure profile text into JSON."
    )
    parser.add_argument("--knowledge-csv", default="knowledge_areas.csv")
    parser.add_argument("--certifications-csv", default="certifications.csv")
    parser.add_argument("--profiles-dir", help="Directory containing .txt profiles")
    parser.add_argument(
        "--from-chroma",
        action="store_true",
        help="Read all CV chunks from ChromaDB, group them by file, and analyze the whole collection",
    )
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR"))
    parser.add_argument("--collection-name", default=os.getenv("COLLECTION_NAME"))
    parser.add_argument(
        "--list-file",
        help="Text file containing comma-separated starter lists for knowledge areas and certifications",
    )
    parser.add_argument("--output", default="skills_certifications_report.json")
    parser.add_argument("--now-year", type=int, default=2026)
    args = parser.parse_args()

    if args.list_file:
        knowledge_areas, certifications = parse_list_file(args.list_file)
        write_knowledge_areas_csv(args.knowledge_csv, knowledge_areas)
        write_certifications_csv(args.certifications_csv, certifications)
        print(
            f"Wrote {args.knowledge_csv} ({len(knowledge_areas)} rows) and "
            f"{args.certifications_csv} ({len(certifications)} rows) from {args.list_file}."
        )
        return

    if not args.profiles_dir:
        if not args.from_chroma:
            parser.error("one of --profiles-dir, --from-chroma, or --list-file is required")

    knowledge_areas = load_knowledge_areas(args.knowledge_csv)
    certifications = load_certifications(args.certifications_csv)

    if args.from_chroma:
        if not args.chroma_dir or not args.collection_name:
            parser.error("--from-chroma requires CHROMA_DIR and COLLECTION_NAME, via args or .env")
        profiles = group_profiles_by_person(
            load_profiles_from_chroma(args.chroma_dir, args.collection_name)
        )
    else:
        profiles = [(profile_id, text, {}) for profile_id, text in load_profiles_from_dir(args.profiles_dir)]

    signals = [
        extract_profile_signals(
            profile_id=profile_id,
            text=text,
            knowledge_areas=knowledge_areas,
            certifications=certifications,
            now_year=args.now_year,
            metadata=metadata,
        )
        for profile_id, text, metadata in profiles
    ]

    payload = {
        "profiles": signals,
        "summary": summarize(signals, certifications=certifications),
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.output} for {len(signals)} profiles.")


if __name__ == "__main__":
    main()
