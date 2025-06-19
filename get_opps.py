import os
import requests
import msal
import match_prompts as mp
import logging

# Configure logger using environment variables for log file locations
LOG_FILE = os.getenv("LOG_FILE", "talentbridge.log")
ERROR_LOG_FILE = os.getenv("ERROR_LOG_FILE", "talentbridge_errors.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Add a separate handler for errors and warnings
error_handler = logging.FileHandler(ERROR_LOG_FILE, mode="a", encoding="utf-8")
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(error_handler)

logger = logging.getLogger(__name__)

# --- 1) Configuration ---
TENANT_ID         = os.getenv("TENANT_ID")
CLIENT_ID         = os.getenv("CLIENT_ID")
CLIENT_SECRET     = os.getenv("CLIENT_SECRET")
DYNAMICS_RESOURCE = os.getenv("DYNAMICS_RESOURCE")  # e.g. "https://avegagroupdev.crm4.dynamics.com"
SCOPE             = [f"{DYNAMICS_RESOURCE}/.default"]
API_VERSION       = "v9.2"

# --- 2) Acquire token ---
app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    client_credential=CLIENT_SECRET
)
token_resp = app.acquire_token_for_client(scopes=SCOPE)
if "access_token" not in token_resp:
    raise Exception(f"Could not acquire token: {token_resp.get('error_description')}")
access_token = token_resp["access_token"]

# --- 3) Common headers ---
headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept":        "application/json",
    "Content-Type":  "application/json; charset=utf-8"
}

# --- 4) Paging loop over Opportunities ---
url = (
    f"{DYNAMICS_RESOURCE}/api/data/{API_VERSION}/opportunities"
    "?$select=opportunityid,name,description,estimatedvalue,actualclosedate"
    "&$orderby=createdon desc"
    "&$top=50"
)

# Track successfully processed opportunities
successfully_loaded = set()

# Load previously processed opportunities from log file
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if "✅ Created Note for Opportunity" in line:
                # Extract the opportunity ID from the log line
                parts = line.strip().split()
                for i, part in enumerate(parts):
                    if part == "Opportunity" and i+1 < len(parts):
                        opp_id = parts[i+1]
                        # Remove trailing punctuation if present
                        opp_id = opp_id.rstrip(":")
                        successfully_loaded.add(opp_id)

while url:
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
    except Exception as e:
        logger.exception(f"Failed to fetch opportunities from {url}")
        continue

    data = resp.json()

    for opp in data.get("value", []):
        opp_id = opp["opportunityid"]

        # Skip if already processed
        if opp_id in successfully_loaded:
            logger.info(f"Skipping already processed opportunity {opp_id}")
            continue

        # 1) Your matching logic
        try:
            selected = mp.adjust_opportunity_with_resume_match(
                opportunityid=opp_id,
                name=opp.get("name", ""),
                description=opp.get("description", ""),
                estimatedvalue=opp.get("estimatedvalue", 0)
            )
            logger.info(f"Opportunity {opp_id} ({opp.get('name', '')}) → Selected consultant: {selected!r}")
        except Exception as e:
            logger.exception(f"Error in matching logic for opportunity {opp_id}")
            continue

        # 2) Skip if there's nothing to write
        if not selected:
            print(f"  ⚠️ No consultant was selected for {opp_id}, skipping update.")
            continue
        else:
            # 3) Build the annotation payload
            note_payload = {
                "subject": f"testar notes - {opp.get('name', '')}",
                "notetext": f"{selected}\n\nOpportunity Name: {opp.get('name', '')}\nOpportunity URL: {DYNAMICS_RESOURCE}/main.aspx?pagetype=entityrecord&etn=opportunity&id={opp_id}",
                # Bind the note to this Opportunity record
                "objectid_opportunity@odata.bind": f"/opportunities({opp_id})"
            }

            # 4) POST to /annotations
            notes_url = f"{DYNAMICS_RESOURCE}/api/data/{API_VERSION}/annotations"
            try:
                note_resp = requests.post(notes_url, headers=headers, json=note_payload)
                note_resp.raise_for_status()
                logger.info(f"✅ Created Note for Opportunity {opp_id}")
                successfully_loaded.add(opp_id)
            except requests.HTTPError:
                logger.error(f"❌ Failed to create Note for {opp_id}: {note_resp.status_code} {note_resp.text}")
            except Exception:
                logger.exception(f"Unexpected error when creating note for {opp_id}")