# cv_processor.py
import openai
import os


openai.api_key = os.getenv("OPENAI_API_KEY")

# This module contains functions to process CVs using OpenAI's GPT-4 model.
# Each function is designed to handle a specific task related to CV processing, such as adjusting, evaluating, translating, rewriting, and generating pitches.  
def adjust_cv(cv_text, adjustment_request):
    """
    Adjusts the CV to match the request details wherving the original writing style.
    Returns the adjusted CV as valid HTML.
    """
    # Define the system message to set the context for the model.
    system_message = (
        "You are a helpful assistant that edits CVs while preserving the original tone and writing style. "
        "Your response must be valid HTML and must be written in the same language as the provided CV. "
        "Any suggestions or improvements should be added as HTML italic text using the <em> tag."
    )
    # Create the user message that includes the CV and the adjustment request.
    user_message = (
        f"Below is my CV. Adjust it to better match the following request while preserving "
        f"the original content and layout as much as possible.\n\n"
        f"Please include any improvement suggestions using HTML <em> tags so that they appear in italics and bold where needed. "
        f"Ensure that the output is complete and valid HTML, and respond in the same language as the CV.\n\n"
        f"Request: {adjustment_request}\n\n"
        f"CV:\n{cv_text}"
    )

    # Call the OpenAI API to get the adjusted CV.
    # The model used is "gpt-4-turbo", which is optimized for chat-based interactions.
    # The temperature parameter controls the randomness of the output.
    # A lower temperature (0.7) makes the output more focused and deterministic.
    resp = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user",   "content": user_message}
        ],
        temperature=0.7,
    )
    # Return the adjusted CV content, stripping any leading or trailing whitespace.
    # The response is expected to be in the form of a chat message, and we access the first choice.
    # The content of the message is accessed using resp.choices[0].message['content'].
    return resp.choices[0].message['content'].strip()


def evaluate_match(cv_text, requirement_text):
    """
    …same docstring…
    """
    system_message = (
        "You are a helpful assistant that evaluates CVs for job matching.  \n"
        "Your response must be valid HTML and in the same language as the provided CV.  \n"
        "Include a section of actionable recommendations, wrapped in:  \n"
        "<div id=\"actionable-recommendations\">…</div>  \n"
        "Also include match probability, effort commentary, strengths, weaknesses, etc."
    )
    user_message = (
        f"Job Requirements:\n{requirement_text}\n\n"
        f"CV:\n{cv_text}\n\n"
        "Please format your actionable recommendations inside a single "
        "<div id=\"actionable-recommendations\">…</div> block."
    )

    resp = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system",  "content": system_message},
            {"role": "user",    "content": user_message}
        ],
        temperature=0.7
    )
    return resp.choices[0].message['content'].strip()



def translate_cv(cv_text, target_language):
    """
    Translates the provided CV text into the target language,
    preserving HTML formatting.
    """
    system_message = (
        "You are an expert translator. Translate the provided CV text into the target language. "
        "Preserve all formatting so that the output remains valid HTML."
    )
    user_message = f"Translate this CV into {target_language}:\n\n{cv_text}"

    resp = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user",   "content": user_message}
        ],
        temperature=0.7,
    )
    return resp.choices[0].message['content'].strip()


def rewrite_cv(cv_text, adjustment_request, target_language, date_threshold):
    """
    Rewrites the Resumé in the target language to match the requirement,
    preserves all entries, and summarizes older assignments into up to
    four bullet points each—highlighting and lifting sentences to match the request.
    Also converts markdown-style **Headings** into HTML <h2> tags and
    **bold**/*italic* into <strong>/<em>.
    """
    system_message = (
        "You are an expert Resumé writer.  \n"
        "1) Rewrite the entire CV in **{lang}**, tailoring every section to the given requirement.  \n"
        "2) Do NOT remove any work experience or assignment entries.  \n"
        # "3) Summarize entries dated before the threshold into no more than four bullet points "
        # "(company, role, dates, one key achievement each).  \n"
        "4) Within each entry—summarized or not—identify and rewrite the exact sentences "
        "that best address the adjustment request, making them stronger.  \n"
        "5) **Markdown conversion rules**:  \n"
        "   - Any standalone line wrapped in double asterisks, e.g. `**Section Title**`, "
        "     must become `<h2>Section Title</h2>`.  \n"
        "   - Any inline `**bold**` becomes `<strong>bold</strong>`.  \n"
        "   - Any inline `*italic*` becomes `<em>italic</em>`.  \n"
        "6) Output must be valid HTML."
    ).format(lang=target_language)

    user_message = (
        f"Requirement: {adjustment_request}\n"
        f"Target language: {target_language}\n"
        f"Summarize assignments older than: {date_threshold}\n\n"
        f"Original CV:\n{cv_text}"
    )

    resp = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system",  "content": system_message},
            {"role": "user",    "content": user_message}
        ],
        temperature=0.7,
    )
    return resp.choices[0].message['content'].strip()


def get_pitch(cv_text, adjustment_request, target_language):
    """
    Generates a third-person cover-letter style pitch based only on the CV and request,
    in the specified language, max 100 words, preserving English technical terms,
    with no added or assumed content.
    """
    system_message = (
        "You are an expert sales-pitch writer. "
        "Based solely on the candidate’s CV and the provided request, write a concise, third-person "
        "cover-letter style pitch in {lang}. Do NOT hallucinate or add any information not explicitly present in the CV. "
        "Preserve any English technical terms or jargon (e.g., “Cloud”, “DevOps”, “API”, “Kubernetes”) unchanged. "
        "Limit the pitch to at most 100 words."
    ).format(lang=target_language)
    
    user_message = (
        f"Adjustment Request:\n{adjustment_request}\n\n"
        f"Candidate CV:\n{cv_text}"
    )

    resp = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system",  "content": system_message},
            {"role": "user",    "content": user_message}
        ],
        temperature=0.3,    # lower creativity to avoid hallucin
        max_tokens=350      # ~100 words
    )
    return resp.choices[0].message['content'].strip()

