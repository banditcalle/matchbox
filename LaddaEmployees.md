# Dokumentation: Ladda in anställda, sanity check och rensning av ChromaDB

## 1. Ladda in anställda och deras CV:n (`get_employees.py`)

### Översikt
`get_employees.py` hämtar konsultdata från Dynamics 365, slår upp bolagsnamn via `get_companies.py` och triggar sedan inläsning av CV:n från SharePoint till ChromaDB via `get_cv_share_point.py`.

### Flöde
1. **Hämtar konsultdata** från Dynamics 365 (t.ex. namn, e-post, bolag, konsult-ID).
2. **Slår upp bolagsnamn** med hjälp av `get_companies.py` baserat på subsidiary-värdet.
3. **Hoppar över** konsulten om bolagsnamnet inte kan bestämmas.
4. **Anropar** `cvsp.run_ingestion` (från `get_cv_share_point.py`) för varje konsult:
    - Skickar med konsultens namn (`FIELD_VALUE`), bolagsnamn (`TOP_FOLDER`) och konsultens unika ID (`CONSULTANT_ID`).
    - Detta säkerställer att varje konsults CV lagras unikt i ChromaDB.
5. **Debug-utskrift** sker för varje konsult (ID, namn, e-post, bolag, m.m.).

### Viktigt
- Om variabeln `ONLY_ONE_CV_PER_FIELD_VALUE` är satt (i `.env`), laddas endast första CV:t per konsult in.
- Om bolagsnamn saknas eller är ogiltigt, hoppar skriptet över konsulten.

---

## 2. Kontrollera innehållet i ChromaDB (`sanity_check_DB.py`)

### Syfte
`sanity_check_DB.py` används för att snabbt kontrollera att ChromaDB innehåller rätt antal och typ av poster efter inläsning.

### Flöde
1. **Ansluter** till ChromaDB med hjälp av miljövariablerna `CHROMA_DIR` och `COLLECTION_NAME`.
2. **Skriver ut** antal poster i kollektionen.
3. **Visar** upp till 100 poster (ID och metadata såsom filnamn, mapp, senaste ändring, chunk-index).

---

## 3. Rensa ChromaDB (`truncate_chroma.py`)

### Syfte
`truncate_chroma.py` används för att rensa (ta bort) alla poster i ChromaDB-kollektionen, t.ex. vid felsökning eller omstart.

### Flöde
1. **Ansluter** till ChromaDB med samma miljövariabler.
2. **Tar bort** alla poster i kollektionen med `col.delete(where={})`.
3. **Bekräftar** att kollektionen nu är tom genom att skriva ut antalet poster.

---

## Miljövariabler (`.env`)
- `CHROMA_DIR` – Sökväg till ChromaDB-databasen.
- `COLLECTION_NAME` – Namn på kollektionen i ChromaDB.
- `ONLY_ONE_CV_PER_FIELD_VALUE` – Om satt till `True`/`1` laddas endast första CV:t per konsult.

---

## Sammanfattning
- **get_employees.py**: Hämtar och laddar in konsulters CV:n till ChromaDB, en post per konsult.
- **sanity_check_DB.py**: Kontrollerar att rätt poster finns i databasen.
- **truncate_chroma.py**: Rensar hela databasen vid behov.

Dessa skript ger tillsammans ett robust flöde för att ladda, kontrollera och underhålla konsultdata i ChromaDB.