# Query Company Skills Report

This document describes how to use `query_company_skills_report.py` to inspect `company_skills_report.json`.

The script is useful after you have generated a company-wide report with:

```powershell
python structure_skills_from_list.py --from-chroma --output company_skills_report.json
```

## Purpose

`query_company_skills_report.py` reads the generated JSON report and lets you:

- see certificate summaries
- see competence area summaries
- list all people who match one certificate
- list all people for all certificates
- export an Excel-friendly flat table
- inspect one grouped person record

## Basic usage

```powershell
python query_company_skills_report.py --mode <mode>
```

If your report file has a different name:

```powershell
python query_company_skills_report.py --report company_skills_report2.json --mode <mode>
```

## Available modes

### `cert-summary`

Shows the certificate summary from `summary.certification_summary`.

Example:

```powershell
python query_company_skills_report.py --mode cert-summary
```

Limit the number of rows:

```powershell
python query_company_skills_report.py --mode cert-summary --top 10
```

### `area-summary`

Shows the competence area summary from `summary.area_summary`.

Example:

```powershell
python query_company_skills_report.py --mode area-summary
```

Top rows only:

```powershell
python query_company_skills_report.py --mode area-summary --top 10
```

### `people-with-cert`

Lists all grouped people who matched one exact certification.

Example:

```powershell
python query_company_skills_report.py --mode people-with-cert --certification "Microsoft Certified: Azure Data Engineer Associate"
```

### `people-with-all-certs`

Prints each certification followed by the people who matched it.

Example:

```powershell
python query_company_skills_report.py --mode people-with-all-certs
```

Top certificates only:

```powershell
python query_company_skills_report.py --mode people-with-all-certs --top 5
```

### `people-with-all-certs-table`

Prints the same information as a flat table with one row per certificate/person pair.

This mode is meant to be easier to copy into Excel.

Columns:

- `certification_name`
- `profiles_with_certification`
- `person_name`
- `company`
- `cv_count`

Example:

```powershell
python query_company_skills_report.py --mode people-with-all-certs-table
```

### `person`

Shows one grouped person result, including merged CV count, certifications, and areas.

Example:

```powershell
python query_company_skills_report.py --mode person --name "Anisur Rahman"
```

You can also use a partial name:

```powershell
python query_company_skills_report.py --mode person --name "Rahman"
```

## Delimiter options

`people-with-all-certs-table` supports custom delimiters.

Available values:

- `tab`
- `semicolon`
- `comma`
- `pipe`

Examples:

```powershell
python query_company_skills_report.py --mode people-with-all-certs-table --delimiter semicolon
python query_company_skills_report.py --mode people-with-all-certs-table --delimiter comma
python query_company_skills_report.py --mode people-with-all-certs-table --delimiter tab
```

For Excel in Swedish regional settings, `semicolon` is often the best choice:

```powershell
python query_company_skills_report.py --mode people-with-all-certs-table --delimiter semicolon
```

## Common workflows

### 1. Regenerate the company report after editing certificate or area lists

```powershell
python structure_skills_from_list.py --from-chroma --output company_skills_report.json
```

### 2. See how many grouped people have each certificate

```powershell
python query_company_skills_report.py --mode cert-summary
```

### 3. See exactly who matched every certificate in a flat table

```powershell
python query_company_skills_report.py --mode people-with-all-certs-table --delimiter semicolon
```

### 4. Investigate one suspicious or duplicated person result

```powershell
python query_company_skills_report.py --mode person --name "Håkan Wikenstål"
```

## Notes

- The report is grouped by person when generated with `--from-chroma`.
- `cv_count` shows how many CV files were merged into that grouped person.
- Matching depends entirely on the contents of `certifications.csv` and `knowledge_areas.csv`.
- If you add new certificates, regenerate `company_skills_report.json` before querying again.
