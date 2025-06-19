import pandas as pd
from typing import Union, List, Dict
import get_cv_share_point as cvsp


# Funktion för att läsa in en Excel-fil och returnera en DataFrame
def read_excel_to_df(
    file_path: str,
    sheet_name: Union[str, int, List[Union[str, int]], None] = 0,
    usecols: Union[str, List[Union[int, str]], None] = None,
    skiprows: Union[int, List[int], None] = None,
    **kwargs
) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
    result = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        usecols=usecols,
        skiprows=skiprows,
        engine="openpyxl",
        **kwargs
    )
    
    # Om användaren bad om alla blad (sheet_name=None) så returneras en dict
    if sheet_name is None:
        return result  # dict
    
    # Om resultatet är en dict (lista av blad), plocka ut det första bladet
    if isinstance(result, dict):
        first_sheet_name = list(result.keys())[0]
        print(f"Varning: flera blad lästa in, returnerar första bladet '{first_sheet_name}'.")
        return result[first_sheet_name]
    
    # Annars är det redan en DataFrame
    return result

if __name__ == "__main__":
    # Exempel på användning
    file_path = "Infile_temp/AvailableConsultants.xlsx"
    
    # Läs in hela första bladet
    df_all = read_excel_to_df(file_path)
    print(df_all.head(), "\n")

    # Iterera över DataFrame och filtrera på kontrakt som är längre än 30 dagar kvar eller saknar slutdatum
    from datetime import datetime, timedelta

    today = pd.Timestamp(datetime.now().date())
    filtered_rows = []
    for idx, row in df_all.iterrows():
        contract_name = row.get('ContractName')
        contract_end = row.get('ContractEndDate')
        # Om slutdatum saknas eller är mer än 30 dagar kvar
        if pd.isnull(contract_end) or (pd.to_datetime(contract_end) - today).days > 30:
            filtered_rows.append(row)

    filtered_df = pd.DataFrame(filtered_rows)
    print("Rader med kontrakt som har mer än 30 dagar kvar eller saknar slutdatum:")
    print(filtered_df)

    # Läs in specifika kolumner (A–C) från bladet "Tillgängliga"
    df_filtered = read_excel_to_df(
        file_path,
        sheet_name="Tillgängliga",
        usecols="A:C"
    )
    print("Första 5 rader från kolumner A–C på bladet 'Tillgängliga':")
    # print(df_filtered.head())

    # Kör cvsp för varje rad med kontrakt som har mer än 30 dagar kvar eller saknar slutdatum
    for idx, row in filtered_df.iterrows():
        firstname = str(row.get('Firstname', '')).strip()
        lastname = str(row.get('Lastname', '')).strip()
        full_name = f"{firstname} {lastname}".strip()
        if full_name:
            print(f"Kör SharePoint-ingest för: {full_name}")
            try:
                cvsp.run_ingestion(full_name)
            except Exception as e:
                print(f"Fel vid körning av cvsp.main för {full_name}: {e}")
