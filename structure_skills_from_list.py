import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


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
    for sentence in sentences:
        s = sentence.lower()
        if any(alias in s for alias in aliases):
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
) -> Dict:
    t = text.lower()

    cert_hits = []
    for cert in certifications:
        terms = [cert.certification_name.lower()] + cert.aliases
        if any(term and term in t for term in terms):
            cert_hits.append(
                {
                    "certification_name": cert.certification_name,
                    "vendor": cert.vendor,
                    "area": cert.area,
                    "level": cert.level,
                }
            )

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
        "areas": area_records,
        "certifications": cert_hits,
    }


def summarize(signals: List[Dict]) -> Dict:
    by_area: Dict[str, Dict] = {}
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

    return {
        "area_summary": sorted(by_area.values(), key=lambda x: x["area"]),
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Structure knowledge and certifications from profile text.")
    parser.add_argument("--knowledge-csv", default="knowledge_areas.csv")
    parser.add_argument("--certifications-csv", default="certifications.csv")
    parser.add_argument("--profiles-dir", required=True, help="Directory containing .txt profiles")
    parser.add_argument("--output", default="skills_certifications_report.json")
    parser.add_argument("--now-year", type=int, default=2026)
    args = parser.parse_args()

    knowledge_areas = load_knowledge_areas(args.knowledge_csv)
    certifications = load_certifications(args.certifications_csv)
    profiles = load_profiles_from_dir(args.profiles_dir)

    signals = [
        extract_profile_signals(
            profile_id=profile_id,
            text=text,
            knowledge_areas=knowledge_areas,
            certifications=certifications,
            now_year=args.now_year,
        )
        for profile_id, text in profiles
    ]

    payload = {
        "profiles": signals,
        "summary": summarize(signals),
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"Wrote {args.output} for {len(signals)} profiles.")


if __name__ == "__main__":
    main()
