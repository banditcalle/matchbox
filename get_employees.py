import os
import msal
import requests
import json
import argparse
from requests.exceptions import HTTPError
import get_companies as gc
import get_cv_share_point as cvsp

API_VER = "v9.2"

def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val

def _get_aad_token():
    CRM_URL   = _require_env("DYNAMICS_RESOURCE")  # e.g. https://xxx.crm4.dynamics.com
    TENANT_ID = _require_env("TENANT_ID")
    CLIENT_ID = _require_env("CLIENT_ID")
    CLIENT_SECRET = _require_env("CLIENT_SECRET")

    app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}"
    )
    token = app.acquire_token_for_client(scopes=[f"{CRM_URL}/.default"])
    if "access_token" not in token:
        raise RuntimeError(token.get("error_description"))
    return token["access_token"], CRM_URL

def _d365_headers(access_token: str):
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata.metadata=minimal",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0"
    }

def _fetch_all(CRM_URL: str, headers: dict, params: dict):
    """
    Follow @odata.nextLink to fetch all pages.
    """
    url = f"{CRM_URL}/api/data/{API_VER}/avega_avegaconsultants"
    results = []
    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("value", []))
        next_link = data.get("@odata.nextLink")

        while next_link:
            resp = requests.get(next_link, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")

    except HTTPError:
        print("REQUEST URL:", resp.url)
        print("STATUS CODE:", resp.status_code)
        try:
            print("OData error payload:\n", json.dumps(resp.json(), indent=2))
        except ValueError:
            print("Response text:\n", resp.text)
        raise

    return results

def get_employees(enable_cleanup: bool = False, only_one_cv: bool | None = None):
    """
    Fetch employees and call cvsp.run_ingestion(FIELD_VALUE, TOP_FOLDER).
    Flags are propagated via env vars that get_cv_share_point.py reads.
    """
    # Propagate feature flags to the ingestion module via environment
    os.environ["ENABLE_CLEANUP"] = "1" if enable_cleanup else "0"
    if only_one_cv is not None:
        os.environ["ONLY_ONE_CV_PER_FIELD_VALUE"] = "1" if only_one_cv else "0"

    access_token, CRM_URL = _get_aad_token()
    headers = _d365_headers(access_token)

    params = {
        "$select": "avega_avegaconsultantid,avega_name,emailaddress,avega_subsidiary,cr6be_matchbox,statecode",
        "$filter": "cr6be_matchbox eq 966730000 and statecode eq 0"  # active consultants
    }

    data = _fetch_all(CRM_URL, headers, params)

    for c in data:
        subsidiary_val = c.get("avega_subsidiary")
        company_name = gc.get_company_label(subsidiary_val) if subsidiary_val is not None else "—"

        # Skip if we can’t resolve the company
        if not company_name or company_name == "—":
            continue

        FIELD_VALUE = c.get("avega_name")
        TOP_FOLDER = company_name

        # Invoke ingestion (now version-aware IDs inside cvsp)
        cvsp.run_ingestion(FIELD_VALUE=FIELD_VALUE, TOP_FOLDER=TOP_FOLDER)

        # Debug printout
        print(f"ID:         {c.get('avega_avegaconsultantid')}")
        print(f"Name:       {FIELD_VALUE}")
        print(f"Email:      {c.get('emailaddress', '—')}")
        print(f"Subsidiary: {subsidiary_val} ({company_name})")
        print(f"Matchbox:   {c.get('cr6be_matchbox')}")
        print(f"Cleanup:    {'ON' if enable_cleanup else 'OFF'} | One-CV: {os.environ.get('ONLY_ONE_CV_PER_FIELD_VALUE', '0')}")
        print("-" * 30)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Dynamics consultants and ingest matching SharePoint CVs.")
    parser.add_argument("--cleanup", action="store_true", help="Enable cleanup of chunks for files no longer present.")
    parser.add_argument("--one-cv", action="store_true", help="Process only the first .docx per person folder.")
    args = parser.parse_args()

    get_employees(enable_cleanup=args.cleanup, only_one_cv=args.one_cv)
