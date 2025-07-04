import os
import msal
import requests
import json
import get_companies as gc
from requests.exceptions import HTTPError
import get_cv_share_point as cvsp

# --- 0. Debug: make sure you’re using the right org URL ---
# CRM_URL = os.getenv("DYNAMICS_RESOURCE")  # e.g. https://avegagroup.crm4.dynamics.com
# print(f">>> Using CRM URL: {CRM_URL}")

# TENANT_ID     = os.getenv("TENANT_ID")
# CLIENT_ID     = os.getenv("CLIENT_ID")
# CLIENT_SECRET = os.getenv("CLIENT_SECRET")
# API_VER       = "v9.2"
# SCOPE         = [f"{CRM_URL}/.default"]

# # --- 1. Get an AAD token ---
# app = msal.ConfidentialClientApplication(
#     client_id=CLIENT_ID,
#     client_credential=CLIENT_SECRET,
#     authority=f"https://login.microsoftonline.com/{TENANT_ID}"
# )
# token = app.acquire_token_for_client(scopes=SCOPE)
# if "access_token" not in token:
#     raise RuntimeError(token.get("error_description"))

# headers = {
#     "Authorization": f"Bearer {token['access_token']}",
#     "Accept": "application/json;odata.metadata=minimal",
#     "OData-MaxVersion": "4.0",
#     "OData-Version": "4.0"
# }

# # --- 2. Build and call the API ---
# url = f"{CRM_URL}/api/data/{API_VER}/avega_avegaconsultants"
# params = {
#     "$select": "avega_avegaconsultantid,avega_name,emailaddress,avega_subsidiary,cr6be_matchbox",
#     "$filter": "cr6be_matchbox eq 966730000"
# }

# try:
#     resp = requests.get(url, headers=headers, params=params)
#     resp.raise_for_status()
# except HTTPError:
#     print("REQUEST URL:", resp.url)
#     print("STATUS CODE:", resp.status_code)
#     try:
#         print("OData error payload:\n", json.dumps(resp.json(), indent=2))
#     except ValueError:
#         print("Response text:\n", resp.text)
#     raise

# # --- 3. Process results (both fields are ints) ---
# data = resp.json().get("value", [])
# for c in data:
#     print("ID:        ", c["avega_avegaconsultantid"])
#     print("Name:      ", c["avega_name"])
#     print("Email:     ", c.get("emailaddress", "—"))
#     print("Subsidiary:", c.get("avega_subsidiary"))   # integer
#     print("Matchbox:  ", c.get("cr6be_matchbox"))    # integer
#     print("-" * 30)

def get_employees():
    """
    Fetch employees and print their info, including company name using gc.get_company_label.
    """
    CRM_URL = os.getenv("DYNAMICS_RESOURCE")
    TENANT_ID     = os.getenv("TENANT_ID")
    CLIENT_ID     = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    API_VER       = "v9.2"
    SCOPE         = [f"{CRM_URL}/.default"]

    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}"
    )
    token = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in token:
        raise RuntimeError(token.get("error_description"))

    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Accept": "application/json;odata.metadata=minimal",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0"
    }

    url = f"{CRM_URL}/api/data/{API_VER}/avega_avegaconsultants"
    params = {
        "$select": "avega_avegaconsultantid,avega_name,emailaddress,avega_subsidiary,cr6be_matchbox",
        "$filter": "cr6be_matchbox eq 966730000 and statecode eq 0" # and statecode eq 0 (bara aktiva konsulter)
    }

    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
    except HTTPError:
        print("REQUEST URL:", resp.url)
        print("STATUS CODE:", resp.status_code)
        try:
            print("OData error payload:\n", json.dumps(resp.json(), indent=2))
        except ValueError:
            print("Response text:\n", resp.text)
        raise

    data = resp.json().get("value", [])
    for c in data:
        subsidiary_val = c.get("avega_subsidiary")
        company_name = gc.get_company_label(subsidiary_val) if subsidiary_val is not None else "—"
        # Set up for cvsp execution
        FIELD_VALUE = c['avega_name']
        TOP_FOLDER = company_name
        # Skip execution if company_name is None or empty/invalid
        if not company_name or company_name == "—":
            continue
        # Call run_ingestion instead of main
        cvsp.run_ingestion(FIELD_VALUE=FIELD_VALUE, TOP_FOLDER=TOP_FOLDER)
        
        # Printout for test
        print(f"ID:        {c['avega_avegaconsultantid']}")
        print(f"Name:      {FIELD_VALUE}")
        print(f"Email:     {c.get('emailaddress', '—')}")
        print(f"Subsidiary: {subsidiary_val} ({company_name})")
        print(f"Matchbox:  {c.get('cr6be_matchbox')}")
        print(f"Would call cvsp.run_ingestion(FIELD_VALUE={FIELD_VALUE}, TOP_FOLDER={TOP_FOLDER})")
        print("-" * 30)

if __name__ == "__main__":
    get_employees()
