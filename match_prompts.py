import os
import openai
import logging
from chromadb import PersistentClient
from chromadb.utils import embedding_functions

# --- Logging setup ---
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
error_handler = logging.FileHandler(ERROR_LOG_FILE, mode="a", encoding="utf-8")
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(error_handler)
logger = logging.getLogger(__name__)

# ── CONFIGURE VIA ENV VARIABLES ────────────────────────────────────────────────
CHROMA_DIR      = os.getenv("CHROMA_DIR")       # e.g. "./chroma_store"
COLLECTION_NAME = os.getenv("COLLECTION_NAME")   # e.g. "resumes"
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "75"))  # default 75%
# ────────────────────────────────────────────────────────────────────────────────

if not CHROMA_DIR or not COLLECTION_NAME:
    logger.error("CHROMA_DIR or COLLECTION_NAME not set in environment.")
    raise RuntimeError("Make sure CHROMA_DIR and COLLECTION_NAME are set in your environment.")

# 1) Open the existing PersistentClient (on‐disk)
client = PersistentClient(path=CHROMA_DIR)

# 2) Load the target collection by name
collection = client.get_collection(name=COLLECTION_NAME)

# Add a compliance standard variable for GDPR protection
compliance_standard = "GDPR"

def adjust_opportunity_with_resume_match(
    opportunityid: str,
    name: str,
    description: str,
    estimatedvalue: str,
    top_k: int = 3
) -> str | None:
    """
    1) Embeds the opportunity text and queries Chroma for top_k resume matches.
    2) Computes cosine-similarity percentages.
    3) Filters out any matches below MATCH_THRESHOLD.
    4) If none remain, returns None; otherwise builds a ChatCompletion prompt
       containing only the qualifying matches and returns the model’s adjusted HTML.
    """

    try:
        # 1) Embed the opportunity text
        combined = f"{name}\n\n{description}"
        emb_resp = openai.Embedding.create(
            model="text-embedding-ada-002",
            input=combined
        )
        query_vec = emb_resp["data"][0]["embedding"]
    except Exception as e:
        logger.exception(f"Failed to embed opportunity text for {opportunityid}")
        return None

    try:
        # 2) Query Chroma for the top_k nearest resumes
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=top_k,
            include=["metadatas", "distances"]
        )
    except Exception as e:
        logger.exception(f"Failed to query ChromaDB for opportunity {opportunityid}")
        return None

    # 3) Turn distances into percentage‐matches and filter by threshold
    matches = []
    for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
        pct = round((1 - dist) * 100, 1)
        title = meta.get("name", "Unknown Candidate")
        if pct >= MATCH_THRESHOLD:
            matches.append((title, pct))

    # 4) If no matches meet the threshold, skip this opportunity
    if not matches:
        logger.info(f"No resume matches above threshold for opportunity {opportunityid}")
        return None

    # 5) Build HTML list of qualifying matches, including source URL if available
    match_html = (
        "<ul>\n"
        + "\n".join(
            f"  <li><strong>{t}</strong>: {p}% match" + (f"<br><a href='{meta.get('source')}'>{meta.get('source')}</a>" if meta.get('source') else "") + "</li>"
            for (t, p), meta in zip(matches, results["metadatas"][0])
        )
        + "\n</ul>"
    )

    # 6) Construct prompt messages, injecting the threshold and compliance standard
    system_message = (
        "You are a helpful assistant that edits sales opportunity descriptions "
        "while preserving the original tone and writing style. "
        f"All processing must comply with the following standard: {compliance_standard}. "
        "If given an empty list of resume matches, respond with an empty reply."
    )

    user_message = (
        f"Here is an opportunity and its top resumes (only those ≥ {MATCH_THRESHOLD}% match):\n\n"
        f"<ul>\n"
        f"  <li><strong>Opportunity ID:</strong> {opportunityid}</li>\n"
        f"  <li><strong>Name:</strong> {name}</li>\n"
        f"  <li><strong>Description:</strong> {description}</li>\n"
        f"  <li><strong>Estimated Value:</strong> {estimatedvalue}</li>\n"
        f"</ul>\n\n"
        "<h3>Top Resume Matches:</h3>\n"
        f"{match_html}\n\n"
        "First, enrich the description to make it more compelling, preserving layout. "
        "Then add a short note explaining why each listed candidate is a strong fit."
    )

    try:
        # 7) Call the OpenAI API
        resp = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user",   "content": user_message}
            ],
            temperature=0.7,
        )
        logger.info(f"OpenAI ChatCompletion successful for opportunity {opportunityid}")
        return resp.choices[0].message["content"].strip()
    except Exception as e:
        logger.exception(f"OpenAI ChatCompletion failed for opportunity {opportunityid}")
        return None
