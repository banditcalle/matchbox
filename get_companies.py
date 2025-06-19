import os
import msal
import requests
import json
import logging
from requests.exceptions import HTTPError

# Set up logging to file for errors only
logging.basicConfig(
    filename=os.path.join(os.path.dirname(__file__), 'logs', 'talentbridge_errors.log'),
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s: %(message)s'
)

# --- Configuration from environment ---
CRM_URL       = os.getenv("DYNAMICS_RESOURCE")  # e.g. https://avegagroup.crm4.dynamics.com
TENANT_ID     = os.getenv("TENANT_ID")
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
API_VER       = "v9.2"
SCOPE         = [f"{CRM_URL}/.default"]

# --- 1. Acquire token ---
app = msal.ConfidentialClientApplication(
    client_id=CLIENT_ID,
    client_credential=CLIENT_SECRET,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}"
)
token_res = app.acquire_token_for_client(scopes=SCOPE)
if "access_token" not in token_res:
    logging.error(f"Auth error: {token_res.get('error_description')}")
    raise RuntimeError(f"Auth error: {token_res.get('error_description')}")
access_token = token_res["access_token"]

headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json;odata.metadata=minimal",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0"
}

# --- 2. Build URL for the option set definition ---
# Note: Name needs to be single-quoted inside the parentheses
url = (
    f"{CRM_URL}/api/data/{API_VER}/"
    "GlobalOptionSetDefinitions(Name='avega_subsidiary')"
)

# --- 3. GET + error handling ---
try:
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
except HTTPError:
    logging.error(f"REQUEST URL: {resp.url}")
    logging.error(f"STATUS CODE: {resp.status_code}")
    try:
        logging.error("OData error payload:\n" + json.dumps(resp.json(), indent=2))
    except ValueError:
        logging.error("Response text:\n" + resp.text)
    raise

# --- 4. Parse and print the option values/labels ---
gos = resp.json()
options = gos.get("Options", [])

def get_company_label(value):
    """
    Given a value, return the corresponding label from the 'avega_subsidiary' option set.
    Logs errors to talentbridge_errors.log, silent on success.
    """
    CRM_URL       = os.getenv("DYNAMICS_RESOURCE")
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
    token_res = app.acquire_token_for_client(scopes=SCOPE)
    if "access_token" not in token_res:
        logging.error(f"Auth error: {token_res.get('error_description')}")
        raise RuntimeError(f"Auth error: {token_res.get('error_description')}")
    access_token = token_res["access_token"]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json;odata.metadata=minimal",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0"
    }

    url = (
        f"{CRM_URL}/api/data/{API_VER}/"
        "GlobalOptionSetDefinitions(Name='avega_subsidiary')"
    )

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
    except HTTPError:
        logging.error(f"REQUEST URL: {resp.url}")
        logging.error(f"STATUS CODE: {resp.status_code}")
        try:
            logging.error("OData error payload:\n" + json.dumps(resp.json(), indent=2))
        except ValueError:
            logging.error("Response text:\n" + resp.text)
        raise

    gos = resp.json()
    options = gos.get("Options", [])

    for opt in options:
        val   = opt.get("Value")
        label = opt.get("Label", {}).get("UserLocalizedLabel", {}).get("Label")
        if val == value:
            return label
    return None

if __name__ == "__main__":
    # Example test: replace 733400013 with a real value as needed
    test_value = 733400013
    label = get_company_label(test_value)
    if label:
        print(f"Label for value {test_value}: {label}")
    else:
        print(f"No label found for value {test_value}.")
