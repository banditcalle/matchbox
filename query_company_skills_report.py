import argparse
import csv
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass


def load_report(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def print_certification_summary(report: dict, top: int | None) -> None:
    rows = report.get("summary", {}).get("certification_summary", [])
    if top is not None:
        rows = rows[:top]

    print("Certification summary")
    for row in rows:
        print(
            f"- {row['certification_name']}: "
            f"{row['profiles_with_certification']} people"
        )


def print_area_summary(report: dict, top: int | None) -> None:
    rows = report.get("summary", {}).get("area_summary", [])
    rows = sorted(rows, key=lambda row: (-row["profiles_with_knowledge"], row["area"]))
    if top is not None:
        rows = rows[:top]

    print("Area summary")
    for row in rows:
        print(
            f"- {row['area']}: {row['profiles_with_knowledge']} people, "
            f"{row['profiles_with_certifications']} with certifications"
        )


def print_experience_summary(report: dict, top: int | None) -> None:
    rows = report.get("summary", {}).get("experience_summary", [])
    if top is not None:
        rows = rows[:top]

    print("Experience summary")
    for row in rows:
        print(
            f"- {row['experience_name']}: "
            f"{row['profiles_with_experience']} people"
        )


def print_profile(profile: dict) -> None:
    print(f"Name: {profile.get('person_name') or profile.get('profile_id')}")
    if profile.get("company"):
        print(f"Company: {profile['company']}")
    if profile.get("cv_count") is not None:
        print(f"CV count: {profile['cv_count']}")

    certs = profile.get("certifications", [])
    experiences = profile.get("experiences", [])
    areas = profile.get("areas", [])

    print("Certifications:")
    if certs:
        for cert in certs:
            print(f"- {cert['certification_name']}")
    else:
        print("- none")

    print("Experiences:")
    if experiences:
        for experience in experiences:
            print(f"- {experience['experience_name']}")
    else:
        print("- none")

    print("Areas:")
    if areas:
        for area in areas:
            print(f"- {area['area']}")
    else:
        print("- none")


def print_people_with_cert(report: dict, certification_name: str) -> None:
    wanted = certification_name.casefold()
    matches = []
    for profile in report.get("profiles", []):
        cert_names = [cert["certification_name"] for cert in profile.get("certifications", [])]
        if any(name.casefold() == wanted for name in cert_names):
            matches.append(profile)

    print(f"People with certification: {certification_name}")
    if not matches:
        print("- none")
        return

    for profile in sorted(matches, key=lambda p: (p.get("person_name") or p.get("profile_id", "")).casefold()):
        name = profile.get("person_name") or profile.get("profile_id")
        company = profile.get("company", "")
        print(f"- {name} ({company})")


def print_people_with_experience(report: dict, experience_name: str) -> None:
    wanted = experience_name.casefold()
    matches = []
    for profile in report.get("profiles", []):
        experience_names = [experience["experience_name"] for experience in profile.get("experiences", [])]
        if any(name.casefold() == wanted for name in experience_names):
            matches.append(profile)

    print(f"People with experience: {experience_name}")
    if not matches:
        print("- none")
        return

    for profile in sorted(matches, key=lambda p: (p.get("person_name") or p.get("profile_id", "")).casefold()):
        name = profile.get("person_name") or profile.get("profile_id")
        company = profile.get("company", "")
        print(f"- {name} ({company})")


def print_people_with_all_certs(report: dict, top: int | None) -> None:
    rows = report.get("summary", {}).get("certification_summary", [])
    if top is not None:
        rows = rows[:top]

    for idx, row in enumerate(rows, start=1):
        if idx > 1:
            print()
        cert_name = row["certification_name"]
        print(
            f"{cert_name}: {row['profiles_with_certification']} people"
        )
        wanted = cert_name.casefold()
        matches = []
        for profile in report.get("profiles", []):
            cert_names = [cert["certification_name"] for cert in profile.get("certifications", [])]
            if any(name.casefold() == wanted for name in cert_names):
                matches.append(profile)

        if not matches:
            print("- none")
            continue

        for profile in sorted(matches, key=lambda p: (p.get("person_name") or p.get("profile_id", "")).casefold()):
            name = profile.get("person_name") or profile.get("profile_id")
            company = profile.get("company", "")
            print(f"- {name} ({company})")


def print_people_with_all_experiences(report: dict, top: int | None) -> None:
    rows = report.get("summary", {}).get("experience_summary", [])
    if top is not None:
        rows = rows[:top]

    for idx, row in enumerate(rows, start=1):
        if idx > 1:
            print()
        experience_name = row["experience_name"]
        print(f"{experience_name}: {row['profiles_with_experience']} people")
        wanted = experience_name.casefold()
        matches = []
        for profile in report.get("profiles", []):
            experience_names = [experience["experience_name"] for experience in profile.get("experiences", [])]
            if any(name.casefold() == wanted for name in experience_names):
                matches.append(profile)

        if not matches:
            print("- none")
            continue

        for profile in sorted(matches, key=lambda p: (p.get("person_name") or p.get("profile_id", "")).casefold()):
            name = profile.get("person_name") or profile.get("profile_id")
            company = profile.get("company", "")
            print(f"- {name} ({company})")


def resolve_delimiter(delimiter_name: str) -> str:
    mapping = {
        "tab": "\t",
        "semicolon": ";",
        "comma": ",",
        "pipe": "|",
    }
    return mapping[delimiter_name]


def write_people_with_all_certs_table(report: dict, top: int | None, delimiter_name: str) -> None:
    rows = report.get("summary", {}).get("certification_summary", [])
    if top is not None:
        rows = rows[:top]

    writer = csv.writer(sys.stdout, delimiter=resolve_delimiter(delimiter_name), lineterminator="\n")
    writer.writerow(
        [
            "certification_name",
            "profiles_with_certification",
            "person_name",
            "company",
            "cv_count",
        ]
    )

    for row in rows:
        cert_name = row["certification_name"]
        wanted = cert_name.casefold()
        matches = []
        for profile in report.get("profiles", []):
            cert_names = [cert["certification_name"] for cert in profile.get("certifications", [])]
            if any(name.casefold() == wanted for name in cert_names):
                matches.append(profile)

        if not matches:
            writer.writerow(
                [
                    cert_name,
                    row["profiles_with_certification"],
                    "",
                    "",
                    "",
                ]
            )
            continue

        for profile in sorted(matches, key=lambda p: (p.get("person_name") or p.get("profile_id", "")).casefold()):
            writer.writerow(
                [
                    cert_name,
                    row["profiles_with_certification"],
                    profile.get("person_name") or profile.get("profile_id"),
                    profile.get("company", ""),
                    profile.get("cv_count", ""),
                ]
            )


def write_people_with_all_experiences_table(report: dict, top: int | None, delimiter_name: str) -> None:
    rows = report.get("summary", {}).get("experience_summary", [])
    if top is not None:
        rows = rows[:top]

    writer = csv.writer(sys.stdout, delimiter=resolve_delimiter(delimiter_name), lineterminator="\n")
    writer.writerow(
        [
            "experience_name",
            "profiles_with_experience",
            "person_name",
            "company",
            "cv_count",
        ]
    )

    for row in rows:
        experience_name = row["experience_name"]
        wanted = experience_name.casefold()
        matches = []
        for profile in report.get("profiles", []):
            experience_names = [experience["experience_name"] for experience in profile.get("experiences", [])]
            if any(name.casefold() == wanted for name in experience_names):
                matches.append(profile)

        if not matches:
            writer.writerow(
                [
                    experience_name,
                    row["profiles_with_experience"],
                    "",
                    "",
                    "",
                ]
            )
            continue

        for profile in sorted(matches, key=lambda p: (p.get("person_name") or p.get("profile_id", "")).casefold()):
            writer.writerow(
                [
                    experience_name,
                    row["profiles_with_experience"],
                    profile.get("person_name") or profile.get("profile_id"),
                    profile.get("company", ""),
                    profile.get("cv_count", ""),
                ]
            )


def print_person(report: dict, name_query: str) -> None:
    wanted = name_query.casefold()
    matches = []
    for profile in report.get("profiles", []):
        name = profile.get("person_name") or profile.get("profile_id", "")
        if wanted in name.casefold():
            matches.append(profile)

    if not matches:
        print(f"No person matched '{name_query}'.")
        return

    for idx, profile in enumerate(matches, start=1):
        if idx > 1:
            print()
        print_profile(profile)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query company_skills_report.json from the terminal.")
    parser.add_argument("--report", default="company_skills_report.json")
    parser.add_argument(
        "--mode",
        choices=[
            "cert-summary",
            "area-summary",
            "experience-summary",
            "people-with-cert",
            "people-with-experience",
            "people-with-all-certs",
            "people-with-all-experiences",
            "people-with-all-certs-table",
            "people-with-all-experiences-table",
            "person",
        ],
        required=True,
    )
    parser.add_argument("--top", type=int, help="Limit number of summary rows.")
    parser.add_argument("--certification", help="Exact certification name to search for.")
    parser.add_argument("--experience", help="Exact experience name to search for.")
    parser.add_argument("--name", help="Full or partial person name to search for.")
    parser.add_argument(
        "--delimiter",
        choices=["tab", "semicolon", "comma", "pipe"],
        default="tab",
        help="Delimiter for table-style output modes.",
    )
    args = parser.parse_args()

    report = load_report(args.report)

    if args.mode == "cert-summary":
        print_certification_summary(report, args.top)
        return

    if args.mode == "area-summary":
        print_area_summary(report, args.top)
        return

    if args.mode == "experience-summary":
        print_experience_summary(report, args.top)
        return

    if args.mode == "people-with-cert":
        if not args.certification:
            parser.error("--mode people-with-cert requires --certification")
        print_people_with_cert(report, args.certification)
        return

    if args.mode == "people-with-experience":
        if not args.experience:
            parser.error("--mode people-with-experience requires --experience")
        print_people_with_experience(report, args.experience)
        return

    if args.mode == "people-with-all-certs":
        print_people_with_all_certs(report, args.top)
        return

    if args.mode == "people-with-all-experiences":
        print_people_with_all_experiences(report, args.top)
        return

    if args.mode == "people-with-all-certs-table":
        write_people_with_all_certs_table(report, args.top, args.delimiter)
        return

    if args.mode == "people-with-all-experiences-table":
        write_people_with_all_experiences_table(report, args.top, args.delimiter)
        return

    if args.mode == "person":
        if not args.name:
            parser.error("--mode person requires --name")
        print_person(report, args.name)


if __name__ == "__main__":
    main()
