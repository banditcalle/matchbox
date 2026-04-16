# Skills and certifications starter taxonomy

This project now uses two separate input lists:

1. `knowledge_areas.csv` for broad knowledge/experience areas.
2. `certifications.csv` for exact certification names.

## Why separate lists

- Knowledge evidence and certification evidence are different concepts.
- It is easier to aggregate by area/vendor when certifications are mapped to an area.
- Duration extraction applies to knowledge areas, not usually to certifications.

## Expected usage

- Use `knowledge_areas.csv` to detect terms in CV text and estimate duration (months/years).
- Use `certifications.csv` to match explicit certificate names.
- Aggregate per person and per area with fields such as:
  - `knowledge_detected`
  - `knowledge_months`
  - `cert_count`
  - `cert_names`

## File formats

### knowledge_areas.csv
- `area`: normalized domain/skill area.
- `vendor`: owning vendor/provider.
- `aliases`: pipe-separated phrases used for matching.

### certifications.csv
- `certification_name`: exact canonical certification title.
- `vendor`: owning vendor/provider.
- `area`: mapped knowledge area.
- `level`: level label (Associate/Professional/etc).
- `aliases`: pipe-separated alternate names and exam codes.

## New structuring script

Use `structure_skills_from_list.py` to create structured profile-level and area-level JSON output from `.txt` profile files.

Example:

```bash
python structure_skills_from_list.py \
  --profiles-dir sample_profiles \
  --output skills_certifications_report.json
```

Output includes:
- Per profile: areas with `knowledge_months`, `cert_count`, and `knowledge_evidence`.
- Summary: counts by area for knowledge and certifications.
